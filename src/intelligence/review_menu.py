"""Private desktop menu. Run python -m src.intelligence.review_menu."""

import os
import tkinter as tk
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox, scrolledtext, ttk

from src.intelligence.review_menu_service import ReviewMenuService

BG = "#f3f5f8"
INK = "#182735"
MUTED = "#617385"
BLUE = "#245cda"


class ReviewMenu:
    def __init__(self, root, service=None):
        self.root = root
        self.service = service or ReviewMenuService()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.busy = False
        self.items = {}
        self.snapshot = None
        self.last_selection = None
        self.view = tk.StringVar(value="Sources")
        self.filter = tk.StringVar(value="Needs review")
        self.search = tk.StringVar()
        self.reviewer = tk.StringVar(value="Ivan")
        self.note = tk.StringVar()
        self.status = tk.StringVar(value="Loading your saved report…")
        self.context = tk.StringVar()
        root.title("Role 3 · Evidence review")
        root.geometry("1180x820")
        root.minsize(940, 680)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Accent.TButton", foreground="white", background=BLUE)
        style.map("Accent.TButton", background=[("active", "#194bc0")])
        style.configure(
            "Treeview",
            font=("Segoe UI", 10),
            rowheight=35,
            background="white",
            fieldbackground="white",
            foreground=INK,
        )
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), padding=8)
        shell = ttk.Frame(root, padding=(24, 20))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(4, weight=1)
        header = ttk.Frame(shell)
        header.grid(row=0, column=0, sticky="ew")
        title = ttk.Frame(header)
        title.pack(side="left", fill="x", expand=True)
        ttk.Label(
            title,
            text="EVIDENCE DESK  /  ROLE 3",
            foreground=MUTED,
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")
        ttk.Label(title, text="Your daily review", font=("Segoe UI Semibold", 25)).pack(
            anchor="w", pady=(3, 2)
        )
        ttk.Label(
            title,
            text="Read the finding. Check the uncertainty. Make the decision.",
            foreground=MUTED,
        ).pack(anchor="w")
        self.load_button = ttk.Button(
            header, text="Load latest GitHub report", command=self.load_latest
        )
        self.load_button.pack(side="right", padx=(10, 0))
        self.save_button = ttk.Button(
            header, text="Save to GitHub", style="Accent.TButton", command=self.publish
        )
        self.save_button.pack(side="right")
        self.summary = ttk.Label(shell, text="", foreground=MUTED)
        self.summary.grid(row=1, column=0, sticky="ew", pady=(18, 5))
        ttk.Label(shell, textvariable=self.context, foreground=MUTED).grid(
            row=2, column=0, sticky="ew", pady=(0, 12)
        )
        controls = ttk.Frame(shell)
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for name in ("Sources", "Skill connections"):
            ttk.Radiobutton(
                controls,
                text=name,
                variable=self.view,
                value=name,
                command=self.render_list,
            ).pack(side="left", padx=(0, 15))
        combo = ttk.Combobox(
            controls,
            textvariable=self.filter,
            values=(
                "Needs review",
                "Approved",
                "Rejected",
                "No connection found",
                "Insufficient evidence",
                "Source approval needed",
                "Check flagged",
                "Check failed",
                "All",
            ),
            state="readonly",
            width=22,
        )
        combo.pack(side="left", padx=(10, 14))
        combo.bind("<<ComboboxSelected>>", lambda event: self.render_list())
        ttk.Label(controls, text="Search").pack(side="left", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.search, width=35).pack(
            side="left", fill="x", expand=True
        )
        self.search.trace_add("write", lambda *args: self.render_list())
        panes = ttk.Panedwindow(shell, orient="horizontal")
        panes.grid(row=4, column=0, sticky="nsew")
        list_frame = ttk.Frame(panes)
        panes.add(list_frame, weight=2)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("title", "status"),
            show="headings",
            selectmode="browse",
            height=6,
        )
        for key, label, width in (
            ("title", "ARTICLE / SKILL", 300),
            ("status", "STATUS", 160),
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=90)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.show_selected)
        self.empty = ttk.Label(list_frame, text="", foreground=MUTED)
        self.empty.pack(anchor="w", pady=(5, 0))
        detail_frame = ttk.Frame(panes, padding=(14, 0, 0, 0))
        panes.add(detail_frame, weight=3)
        detail_header = ttk.Frame(detail_frame)
        detail_header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            detail_header,
            text="EVIDENCE & REMAINING CHECKS",
            font=("Segoe UI Semibold", 10),
            foreground=MUTED,
        ).pack(side="left")
        self.link_button = ttk.Button(
            detail_header, text="Open original source ↗", command=self.open_source
        )
        self.link_button.pack(side="right")
        self.details = scrolledtext.ScrolledText(
            detail_frame,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            padx=14,
            pady=12,
            background="white",
            foreground=INK,
            height=10,
            width=65,
        )
        self.details.pack(fill="both", expand=True)
        self._details(
            "Select an item above to read its AI summary and the points that need your attention."
        )
        identity = ttk.Frame(shell)
        identity.grid(row=5, column=0, sticky="ew", pady=(12, 8))
        ttk.Label(identity, text="Reviewer").pack(side="left", padx=(0, 8))
        ttk.Entry(identity, textvariable=self.reviewer, width=17).pack(
            side="left", padx=(0, 16)
        )
        ttk.Label(identity, text="Review note (required for rejection)").pack(
            side="left", padx=(0, 8)
        )
        ttk.Entry(identity, textvariable=self.note).pack(
            side="left", fill="x", expand=True
        )
        footer = ttk.Frame(shell)
        footer.grid(row=6, column=0, sticky="ew")
        self.approve_button = ttk.Button(
            footer,
            text="✓  Approve",
            style="Accent.TButton",
            command=lambda: self.decide("approve"),
        )
        self.approve_button.pack(side="left")
        self.reject_button = ttk.Button(
            footer, text="Reject", command=lambda: self.decide("reject")
        )
        self.reject_button.pack(side="left", padx=9)
        self.recheck_button = ttk.Button(
            footer, text="Ask AI to check again", command=self.recheck
        )
        self.recheck_button.pack(side="left")
        self.key_button = ttk.Button(footer, text="AI key…", command=self.configure_key)
        self.key_button.pack(side="right")
        self.progress = ttk.Progressbar(shell, mode="indeterminate")
        self.progress.grid(row=7, column=0, sticky="ew", pady=(12, 6))
        ttk.Label(
            shell, textvariable=self.status, foreground=MUTED, wraplength=1080
        ).grid(row=8, column=0, sticky="ew")
        self.run(
            "Loading your saved report…", self.service.snapshot, self.apply_snapshot
        )

    def _details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def selected(self):
        selection = self.tree.selection()
        return self.items.get(selection[0]) if selection else None

    def render_list(self):
        if not self.snapshot:
            return
        previous = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        query = self.search.get().strip().casefold()
        visible = []
        for item in self.items.values():
            if (item.kind == "source") != (self.view.get() == "Sources"):
                continue
            if self.filter.get() != "All" and item.status != self.filter.get():
                continue
            if query and query not in (item.title + " " + item.skill).casefold():
                continue
            visible.append(item)
        for item in visible:
            title = item.skill + " — " + item.title if item.skill else item.title
            self.tree.insert(
                "",
                "end",
                iid=item.key,
                values=(title, item.status),
            )
        self.empty.configure(
            text=""
            if visible
            else "No items match this view. Choose All to include cached negative assessments."
        )
        key = (
            previous[0]
            if previous and any(i.key == previous[0] for i in visible)
            else visible[0].key
            if visible
            else None
        )
        if key:
            self.tree.selection_set(key)
            self.tree.focus(key)
        else:
            self._details(
                "No review item selected. The coverage totals above show any work still pending."
            )
        self.show_selected()

    def apply_snapshot(self, snapshot):
        self.snapshot = snapshot
        self.items = {i.key: i for i in snapshot["items"]}
        stats = snapshot["stats"]
        self.summary.configure(
            text=f"{sum(i.kind == 'source' for i in self.items.values())} sources  ·  {stats['completed_pairs']:,} skill/article pairs checked  ·  {stats['pending_pairs']:,} still queued  ·  {stats['articles_awaiting_shared_review']} sources awaiting shared review"
        )
        run = snapshot["run"]
        self.context.set(
            (
                f"GitHub run #{run['run_id']} · {run['conclusion']} · {run['updated_at']}"
                if run
                else "Saved repository snapshot — load the latest GitHub report before your daily review."
            )
            + ("  ·  Local changes ready to save" if snapshot["pending_paths"] else "")
        )
        self.render_list()

    def show_selected(self, event=None):
        item = self.selected()
        selected_key = item.key if item else None
        if selected_key != self.last_selection:
            self.note.set("")
            self.last_selection = selected_key
        if item:
            self._details(item.details)
        self.buttons()

    def buttons(self):
        item = self.selected()
        for button in (self.load_button, self.key_button):
            button.configure(state="disabled" if self.busy else "normal")
        self.save_button.configure(
            state="normal"
            if not self.busy and self.snapshot and self.snapshot["pending_paths"]
            else "disabled"
        )
        self.approve_button.configure(
            state="normal" if not self.busy and item and item.approvable else "disabled"
        )
        for button in (self.reject_button, self.recheck_button, self.link_button):
            button.configure(state="normal" if not self.busy and item else "disabled")
        if item and item.block_reason and not self.busy:
            self.status.set(item.block_reason)

    def run(
        self,
        message,
        operation,
        callback,
        success="Ready. Your decisions are saved locally until you click Save to GitHub.",
    ):
        if self.busy:
            return
        self.busy = True
        self.status.set(message)
        self.buttons()
        self.progress.start(12)
        future = self.executor.submit(operation)

        def poll():
            if not future.done():
                self.root.after(100, poll)
                return
            self.busy = False
            self.progress.stop()
            try:
                value = future.result()
                result_message = callback(value)
                self.status.set(
                    result_message if isinstance(result_message, str) else success
                )
            except Exception as error:  # noqa: BLE001 -- GUI boundary keeps failed actions visible.
                self.status.set("Action did not complete. Previous records are kept.")
                messagebox.showerror(
                    "Review action could not finish", str(error)[:700], parent=self.root
                )
            self.buttons()

        self.root.after(100, poll)

    def load_latest(self):
        self.run(
            "Loading the latest completed GitHub report…",
            self.service.refresh,
            self.apply_snapshot,
            "Latest report loaded. Start with the highlighted findings and remaining checks.",
        )

    def decide(self, decision):
        item = self.selected()
        if not item:
            return
        reviewer, note = self.reviewer.get(), self.note.get()
        self.run(
            "Recording your decision…",
            lambda: self.service.decide(
                item.key, item.version, decision, reviewer, note
            ),
            self.apply_snapshot,
        )

    def recheck(self):
        item = self.selected()
        if not item:
            return

        def completed(result):
            self.apply_snapshot(result["snapshot"])
            if result["failed"]:
                messagebox.showinfo(
                    "AI check remains pending",
                    "The AI check could not complete. No approval was recorded. Previous evidence is preserved; try again later.",
                    parent=self.root,
                )
                return "AI check did not complete. The previous review is shown; no approval was recorded."
            return None

        self.run(
            "AI is rechecking this item. Availability fallback may take a few minutes…",
            lambda: self.service.recheck(item.key, item.version),
            completed,
            "AI recheck finished. Review the updated evidence before deciding.",
        )

    def publish(self):
        self.run(
            "Saving reviewed decisions and their evidence records to GitHub…",
            self.service.publish,
            self.apply_snapshot,
            "Saved to GitHub. The daily workflow can now use your recorded decisions.",
        )

    def open_source(self):
        item = self.selected()
        if item:
            self.run(
                "Checking the original publisher link…",
                lambda: self.service.trusted_url(item.key, item.version),
                lambda url: webbrowser.open(url),
                "Opened the configured original publisher in your browser.",
            )

    def configure_key(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("AI key for this session")
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Gemini API key", font=("Segoe UI Semibold", 12)).pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text="Used only on this laptop for this session. Never saved to a file or GitHub.",
            wraplength=420,
        ).pack(anchor="w", pady=(5, 12))
        value = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=value, show="•", width=48)
        entry.pack(fill="x")
        entry.focus_set()

        def save():
            if not value.get().strip():
                return
            os.environ["GEMINI_API_KEY"] = value.get().strip()
            value.set("")
            dialog.destroy()
            self.status.set("AI key is available for this session.")

        ttk.Button(
            frame, text="Use for this session", style="Accent.TButton", command=save
        ).pack(anchor="e", pady=(14, 0))

    def close(self):
        if self.busy:
            messagebox.showinfo(
                "Action in progress",
                "Please let the current review action finish before closing the menu.",
                parent=self.root,
            )
            return
        self.executor.shutdown(wait=False)
        self.root.destroy()


def main():
    root = tk.Tk()
    ReviewMenu(root)
    root.mainloop()


if __name__ == "__main__":
    main()
