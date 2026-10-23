"""HTTP adapters; scoring, scenarios and course selection stay in their modules."""

from uuid import uuid4
from threading import BoundedSemaphore

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from src.ingestion.onet_api import get_onet_role, list_onet_roles
from src.intelligence.feeds import DEFAULT_SNAPSHOTS, get_refresh_status
from src.intelligence.impacts import get_evidence_chain_response
from src.profiles.cv_parser import MAX_BYTES, CVParseError
from src.profiles.intake import validate_profile
from src.profiles.samples import sample_cv_pdf
from src.schemas.profile import ProfileConstraints, ProfileSkill, SkillsProfile
from src.schemas.role import Contract
from src.schemas.roadmap import ScenarioId

router = APIRouter()
extraction_slots = BoundedSemaphore(2)


class ReviewRequest(Contract):
    revision: int = Field(ge=0)
    skills: list[ProfileSkill] = Field(max_length=500)
    desired_role_id: str | None = None
    interests: list[str] = Field(default_factory=list, max_length=20)
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)


class PlanRequest(Contract):
    revision: int = Field(ge=0)
    role_id: str = Field(max_length=100)
    scenario_id: ScenarioId = "baseline"
    selected_software_skill_ids: list[str] = Field(default_factory=list, max_length=50)


def session_for(request, token):
    return request.app.state.sessions.get(token)


def require_review(session, revision):
    if session.revision != revision:
        raise HTTPException(409, "Your profile changed. Review it and refresh your matches.")
    if not session.reviewed:
        raise HTTPException(409, "Review and confirm your extracted skills first.")


def require_role(backend, role_id):
    if role_id not in {role.role_id for role in backend.catalog.roles}:
        raise HTTPException(404, "This occupation is not in the current catalog.")


def extract_session(request, content, filename):
    if not extraction_slots.acquire(blocking=False):
        raise HTTPException(429, "CV processing is busy. Please try again shortly.")
    try:
        profile = request.app.state.backend.extract_profile(
            "synthetic:" + uuid4().hex, content, filename)
    except CVParseError as error:
        raise HTTPException(422, {"code": error.code, "message": str(error)}) from error
    finally:
        extraction_slots.release()
    token = request.app.state.sessions.create(profile)
    return {"session_id": token, "revision": 0, "profile": profile.model_dump(mode="json")}


@router.post("/profiles/upload", openapi_extra={"requestBody": {
    "required": True, "content": {"application/octet-stream": {
        "schema": {"type": "string", "format": "binary"}}}}})
async def upload(request: Request, x_filename: str = Header(default="cv.pdf", max_length=255)):
    # Bound the raw body before a file parser or spool can buffer it.
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, "Upload exceeds 2 MiB. Choose a smaller CV.")
        content.extend(chunk)
    return await run_in_threadpool(extract_session, request, bytes(content), x_filename)


@router.get("/samples/graduate.pdf")
def download_sample():
    return Response(sample_cv_pdf(), media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="fictional-graduate-cv.pdf"'})


@router.post("/profiles/sample")
def use_sample(request: Request):
    return extract_session(request, sample_cv_pdf(), "fictional-graduate-cv.pdf")


@router.post("/profiles/manual")
def manual_fallback(request: Request):
    profile = request.app.state.backend.create_profile("synthetic:" + uuid4().hex, [])
    token = request.app.state.sessions.create(profile)
    return {"session_id": token, "revision": 0, "profile": profile.model_dump(mode="json")}


@router.delete("/profiles/current", status_code=204)
def forget_profile(request: Request, x_session_id: str = Header()):
    request.app.state.sessions.delete(x_session_id)


@router.get("/skills")
def skills(request: Request, q: str = Query(default="", max_length=100)):
    terms = q.casefold().split()
    rows = [skill for skill in request.app.state.backend.catalog.taxonomy.skills
            if all(term in " ".join([skill.label, *skill.aliases]).casefold() for term in terms)]
    return {"skills": [{"skill_id": skill.skill_id, "label": skill.label}
                       for skill in rows[:25]], "total": len(rows)}


@router.get("/roles")
def roles(request: Request, q: str = Query(default="", max_length=100),
          offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100)):
    return list_onet_roles(request.app.state.backend.catalog, query=q, offset=offset, limit=limit)


@router.get("/roles/{role_id}")
def role_detail(request: Request, role_id: str):
    backend = request.app.state.backend
    require_role(backend, role_id)
    return get_onet_role(backend.catalog, role_id)


@router.patch("/profiles/current")
def review(request: Request, body: ReviewRequest, x_session_id: str = Header()):
    session = session_for(request, x_session_id)
    backend = request.app.state.backend
    with session.lock:
        if body.revision != session.revision:
            raise HTTPException(409, "Your profile changed. Upload or review it again.")
        if any(skill.confirmation != "confirmed" for skill in body.skills):
            raise HTTPException(422, "Retain only the skills you have explicitly confirmed.")
        try:
            profile = backend.review_profile(session.profile, body.skills)
            payload = profile.model_dump()
            payload.update(desired_role_id=body.desired_role_id, interests=body.interests,
                           constraints=body.constraints.model_dump())
            profile = validate_profile(SkillsProfile.model_validate(payload), backend.catalog)
        except ValueError as error:
            raise HTTPException(422, "Check the selected skills, target role and constraints.") from error
        session.profile = profile
        session.revision += 1
        session.reviewed = True
        return {"revision": session.revision, "profile": profile.model_dump(mode="json")}


@router.get("/matches")
def matches(request: Request, revision: int = Query(ge=0),
            x_session_id: str = Header(), top_n: int = Query(default=10, ge=1, le=50)):
    session = session_for(request, x_session_id)
    with session.lock:
        require_review(session, revision)
        rows = request.app.state.backend.match(session.profile, top_n=top_n)
        return {"revision": session.revision,
                "matches": [row.model_dump(mode="json") for row in rows]}


@router.get("/roles/{role_id}/outlook")
def outlook(request: Request, role_id: str, scenario_id: ScenarioId = "baseline"):
    backend = request.app.state.backend
    require_role(backend, role_id)
    available = backend.outlook(role_id).available_scenarios
    if scenario_id not in available:
        raise HTTPException(422, "This scenario is unavailable for the selected occupation.")
    return backend.outlook(role_id, scenario_id).model_dump(mode="json")


@router.get("/roles/{role_id}/evidence")
def evidence(request: Request, role_id: str):
    backend = request.app.state.backend
    require_role(backend, role_id)
    return get_evidence_chain_response(role_id, catalog=backend.catalog)


@router.get("/evidence/status")
def evidence_status():
    status = get_refresh_status(DEFAULT_SNAPSHOTS / "onet/last_refresh.json")
    return {"refresh": status.model_dump(mode="json") if status else None}


@router.get("/roles/{role_id}/skill-evidence")
def skill_evidence(request: Request, role_id: str):
    backend = request.app.state.backend
    require_role(backend, role_id)
    try:
        result = backend.skill_evidence(role_id)
    except (OSError, ValueError) as error:
        raise HTTPException(503, "Skill evidence is temporarily unavailable.") from error
    labels = {skill.skill_id: skill.label for skill in backend.catalog.taxonomy.skills}
    return {**result, "approved_conditional_skill_evidence": [
        {**row, "skill_label": labels.get(row["skill_id"], row["skill_id"])}
        for row in result["approved_conditional_skill_evidence"]
    ]}


@router.get("/roles/{role_id}/impacts")
def role_impacts(request: Request, role_id: str):
    backend = request.app.state.backend
    require_role(backend, role_id)
    try:
        return backend.role_impacts(role_id)
    except (OSError, ValueError) as error:
        raise HTTPException(503, "Role impact evidence is temporarily unavailable.") from error


@router.post("/pathways")
def pathway(request: Request, body: PlanRequest, x_session_id: str = Header()):
    session = session_for(request, x_session_id)
    backend = request.app.state.backend
    require_role(backend, body.role_id)
    with session.lock:
        require_review(session, body.revision)
        if body.scenario_id not in backend.outlook(body.role_id).available_scenarios:
            raise HTTPException(422, "This scenario is unavailable for the selected occupation.")
        match = backend.matcher.match_role(session.profile, body.role_id)
        allowed = {item.skill_id for item in match.software_learning_options}
        if not set(body.selected_software_skill_ids) <= allowed:
            raise HTTPException(422, "Choose only the available optional software skills.")
        result = backend.learning_plan(session.profile, body.role_id, body.scenario_id,
            selected_software_skill_ids=body.selected_software_skill_ids)
        return {"revision": session.revision, **result.model_dump(mode="json")}


@router.get("/courses/status")
def course_status(request: Request):
    from src.reskilling.course_catalog import CourseCatalogError

    try:
        catalog = request.app.state.backend.course_store.load()
    except (OSError, CourseCatalogError) as error:
        raise HTTPException(503, "The verified course catalog is temporarily unavailable.") from error
    return {
        "status": "available" if catalog.courses else "empty",
        "verified_course_count": len(catalog.courses),
        "updated_at": catalog.updated_at.isoformat() if catalog.updated_at else None,
        "mode": "verified_cache",
    }
