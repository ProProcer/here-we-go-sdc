# Running FutureReady AI on Replit

## Run
- Click **Run** to start the `Start application` workflow.
- It installs the frontend's locked dependencies, runs the TypeScript/Vite build, and starts `python -m src.main`.
- Python dependencies are installed from `requirements.txt` into Replit's managed `.pythonlibs` environment. Do not create a virtual environment.
- Python 3.12 and Node.js 22 are used. Keep the existing React frontend and FastAPI backend structure.
- FastAPI listens on `0.0.0.0:5000`, serving both `frontend/dist` and `/api/v2`. No second frontend server is needed.
- After frontend changes, rerun the workflow to rebuild. The health endpoint is `/health`.
- Startup commands clear `LD_LIBRARY_PATH`; preserve that wrapper when changing commands.

## Capabilities and limits
- No external credentials are required to open the app, extract skills locally, review them, match careers, or use cached learning resources.
- AI proficiency assessment, generated explanations, and translations use the providers described in `docs/AI_PROVIDERS.md`. Provider settings have been added through Replit Secrets; live provider calls have not been verified.
- Never put provider credentials in source files or chat; use Replit Secrets.
- Use fictional CVs for testing. Sessions are held in memory, expire after one hour, and disappear on restart. Run only one server worker.
- The development content security policy permits embedding by the Replit editor; production retains its no-embedding policy.
- Publishing has not been performed or verified as part of the local setup.

## Checks
- `env -u LD_LIBRARY_PATH npm --prefix frontend run build`
- `env -u LD_LIBRARY_PATH python -m unittest discover -s tests -p test_proficiency_matching.py -q`
- For the complete HTTP test suite, install the dependencies from `requirements-dev.txt` first.
