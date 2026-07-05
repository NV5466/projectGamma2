from __future__ import annotations

from pathlib import Path
import ctypes
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gamma_app.registry import ALLOWED_FAMILIES, read_seed_registry_entries
from gamma_app.runtime import default_threshold_profile_path, resource_path
from gamma_app.runner import add_capture_to_dataset, analyze_path, validate_dataset
from gamma_app.threshold_profiles import load_threshold_profile, save_threshold_profile
from gamma_app.validation_store import ValidationStore
from gamma_app.waveform_sets import DEFAULT_WAVEFORM_LIBRARY, import_waveforms, list_waveform_sets, read_manifest, sanitize_set_id


LOGO_PATH = resource_path("assets/gamma_logo.png")
ICON_PATH = resource_path("assets/gamma_logo.ico")
APP_USER_MODEL_ID = "Gamma.ElectroStat.App"


class GammaApp(tk.Tk):
    def __init__(self) -> None:
        _set_windows_app_id()
        super().__init__()
        self.title("Gamma")
        self.geometry("1180x760")
        if ICON_PATH.exists():
            self.iconbitmap(default=str(ICON_PATH))
        self.logo_image = self._load_logo()
        if self.logo_image is not None:
            self.iconphoto(False, self.logo_image)
        self.analyze_input_var = tk.StringVar(value="validation/fixtures/three_signature_smoke")
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=8)
        if self.logo_image is not None:
            logo = ttk.Label(header, image=self.logo_image)
            logo.pack(side="left", padx=(0, 12))
        ttk.Label(header, text="Gamma", font=("Segoe UI", 18, "bold")).pack(side="left")
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        self.waveform_sets_tab = ttk.Frame(tabs)
        self.analyze_tab = ttk.Frame(tabs)
        self.batch_tab = ttk.Frame(tabs)
        self.validation_tab = ttk.Frame(tabs)
        self.results_tab = ttk.Frame(tabs)
        self.settings_tab = ttk.Frame(tabs)
        tabs.add(self.waveform_sets_tab, text="Waveform Sets")
        tabs.add(self.analyze_tab, text="Analyze Capture")
        tabs.add(self.batch_tab, text="Batch Campaign")
        tabs.add(self.validation_tab, text="Validation Dataset")
        tabs.add(self.results_tab, text="Results / Reports")
        tabs.add(self.settings_tab, text="Settings / Thresholds")
        self._build_waveform_sets()
        self._build_analyze(self.analyze_tab, batch=False)
        self._build_analyze(self.batch_tab, batch=True)
        self._build_validation()
        self._build_results()
        self._build_settings()

    def _build_analyze(self, parent: ttk.Frame, *, batch: bool) -> None:
        title = "Batch capture folder" if batch else "Capture file or folder"
        input_var = tk.StringVar(value="validation/fixtures/three_signature_smoke") if batch else self.analyze_input_var
        out_var = tk.StringVar(value="outputs/batch_campaign" if batch else "outputs/gui_analysis")
        profile_var = tk.StringVar(value=str(default_threshold_profile_path()))
        family_vars = {family: tk.BooleanVar(value=True) for family in sorted(ALLOWED_FAMILIES)}
        row = 0
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(parent, textvariable=input_var, width=90).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(parent, text="Browse", command=lambda: self._browse_input(input_var)).grid(row=row, column=2, padx=8)
        row += 1
        ttk.Label(parent, text="Output folder").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(parent, textvariable=out_var, width=90).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(parent, text="Browse", command=lambda: self._browse_dir(out_var)).grid(row=row, column=2, padx=8)
        row += 1
        ttk.Label(parent, text="Threshold profile").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(parent, textvariable=profile_var, width=90).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        row += 1
        family_frame = ttk.LabelFrame(parent, text="Seed/family filter")
        family_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=8, pady=6)
        for idx, (family, var) in enumerate(family_vars.items()):
            ttk.Checkbutton(family_frame, text=family, variable=var).grid(row=0, column=idx, padx=8, pady=4)
        row += 1
        status = tk.StringVar(value="Ready")
        ttk.Label(parent, textvariable=status).grid(row=row, column=0, columnspan=3, sticky="w", padx=8, pady=6)
        row += 1
        table = self._result_table(parent, row)
        parent.columnconfigure(1, weight=1)

        def run() -> None:
            try:
                selected = {family for family, var in family_vars.items() if var.get()}
                result = analyze_path(
                    input_var.get(),
                    out_var.get(),
                    threshold_profile_path=profile_var.get(),
                    family_filter=selected or None,
                    mode="batch" if batch else "diagnostic",
                )
                status.set(f"Complete: {len(result.case_results)} capture(s), outputs in {out_var.get()}")
                self._load_table(table, Path(out_var.get()) / "campaign_results.csv")
            except Exception as exc:
                messagebox.showerror("Gamma analysis failed", repr(exc))

        ttk.Button(parent, text="Run Analysis", command=run).grid(row=row + 1, column=0, sticky="w", padx=8, pady=8)

    def _build_waveform_sets(self) -> None:
        parent = self.waveform_sets_tab
        set_var = tk.StringVar(value="bench_run_001")
        library_var = tk.StringVar(value=str(DEFAULT_WAVEFORM_LIBRARY))
        selected_sources: list[str] = []
        status = tk.StringVar(value="Create a set, select files/folders, then import.")

        ttk.Label(parent, text="Waveform set name").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(parent, textvariable=set_var, width=48).grid(row=0, column=1, sticky="ew", padx=8, pady=6)
        ttk.Label(parent, text="Library root").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(parent, textvariable=library_var, width=90).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(parent, text="Browse", command=lambda: self._browse_dir(library_var)).grid(row=1, column=2, padx=8)

        source_box = tk.Listbox(parent, height=7)
        source_box.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=8, pady=6)

        def refresh_sources() -> None:
            source_box.delete(0, "end")
            for source in selected_sources:
                source_box.insert("end", source)

        def add_files() -> None:
            files = filedialog.askopenfilenames(filetypes=[("Gamma NPZ captures", "*.npz"), ("All files", "*.*")])
            selected_sources.extend(files)
            refresh_sources()

        def add_folder() -> None:
            folder = filedialog.askdirectory()
            if folder:
                selected_sources.append(folder)
                refresh_sources()

        def clear_sources() -> None:
            selected_sources.clear()
            refresh_sources()

        button_row = ttk.Frame(parent)
        button_row.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=6)
        ttk.Button(button_row, text="Select Capture Files", command=add_files).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Select Folder", command=add_folder).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Clear", command=clear_sources).pack(side="left")

        table = self._result_table(parent, 6)

        def import_set() -> None:
            try:
                waveform_set, imported, warnings = import_waveforms(
                    selected_sources,
                    set_var.get(),
                    library_root=library_var.get(),
                    notes=f"# {set_var.get()}\n",
                )
                status.set(f"Imported {len(imported)} capture(s) into {waveform_set.root}")
                self._load_waveform_manifest_table(table, waveform_set.manifest_path)
                if warnings:
                    messagebox.showwarning("Waveform import warnings", "\n".join(warnings[:20]))
            except Exception as exc:
                messagebox.showerror("Waveform import failed", repr(exc))

        def use_in_analyze() -> None:
            path = Path(library_var.get()) / sanitize_set_id(set_var.get()) / "captures"
            self.analyze_input_var.set(str(path))
            status.set(f"Analyze tab input set to {path}")

        def load_existing() -> None:
            sets = list_waveform_sets(library_var.get())
            if not sets:
                messagebox.showinfo("Waveform sets", "No waveform sets found in this library root.")
                return
            set_var.set(sets[-1].set_id)
            self._load_waveform_manifest_table(table, sets[-1].manifest_path)
            status.set(f"Loaded {sets[-1].root}")

        ttk.Button(parent, text="Import Into Set", command=import_set).grid(row=4, column=0, sticky="w", padx=8, pady=8)
        ttk.Button(parent, text="Use Set In Analyze Tab", command=use_in_analyze).grid(row=4, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(parent, text="Load Latest Existing Set", command=load_existing).grid(row=4, column=2, sticky="w", padx=8, pady=8)
        ttk.Label(parent, textvariable=status).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)

    def _build_validation(self) -> None:
        parent = self.validation_tab
        dataset_var = tk.StringVar(value="outputs/validation/gamma_validation.db")
        source_var = tk.StringVar(value="validation/fixtures/three_signature_smoke/case_001_relay_kick.npz")
        capture_var = tk.StringVar()
        label_var = tk.StringVar(value="relay_coil_inductive_kick")
        no_fault_var = tk.BooleanVar(value=False)
        notes = tk.Text(parent, height=4)
        fields = [
            ("Dataset SQLite path", dataset_var, self._browse_save),
            ("Capture source file", source_var, self._browse_input),
            ("Capture ID", capture_var, None),
            ("Ground truth seed label", label_var, None),
        ]
        for row, (label, var, browse) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=6)
            ttk.Entry(parent, textvariable=var, width=90).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
            if browse:
                ttk.Button(parent, text="Browse", command=lambda v=var, b=browse: b(v)).grid(row=row, column=2, padx=8)
        ttk.Checkbutton(parent, text="No-fault/control label", variable=no_fault_var).grid(row=4, column=1, sticky="w", padx=8)
        ttk.Label(parent, text="Notes").grid(row=5, column=0, sticky="nw", padx=8, pady=6)
        notes.grid(row=5, column=1, sticky="ew", padx=8, pady=6)
        table = self._result_table(parent, 8)

        def add_case() -> None:
            try:
                add_capture_to_dataset(
                    dataset_var.get(),
                    source_var.get(),
                    capture_id=capture_var.get() or None,
                    seed_label=label_var.get() or None,
                    no_fault_control=no_fault_var.get(),
                    notes=notes.get("1.0", "end").strip() or None,
                )
                self._load_dataset_table(table, dataset_var.get())
            except Exception as exc:
                messagebox.showerror("Dataset add failed", repr(exc))

        def validate() -> None:
            try:
                out_dir = str(Path(dataset_var.get()).with_suffix("")) + "_run"
                validate_dataset(dataset_var.get(), out_dir)
                self._load_table(table, Path(out_dir) / "validation_summary.csv")
                messagebox.showinfo("Validation complete", f"Wrote {out_dir}")
            except Exception as exc:
                messagebox.showerror("Validation failed", repr(exc))

        ttk.Button(parent, text="Add Capture To Dataset", command=add_case).grid(row=6, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(parent, text="Run Validation Summary", command=validate).grid(row=6, column=1, padx=180, pady=8, sticky="w")
        parent.columnconfigure(1, weight=1)

    def _build_results(self) -> None:
        parent = self.results_tab
        result_var = tk.StringVar(value="outputs/gui_analysis")
        ttk.Label(parent, text="Result folder").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ttk.Entry(parent, textvariable=result_var, width=90).grid(row=0, column=1, padx=8, pady=6, sticky="ew")
        ttk.Button(parent, text="Browse", command=lambda: self._browse_dir(result_var)).grid(row=0, column=2, padx=8)
        table = self._result_table(parent, 2)
        report = tk.Text(parent, height=14)
        report.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)

        def refresh() -> None:
            out = Path(result_var.get())
            self._load_table(table, out / "campaign_results.csv")
            reports = sorted((out / "reports").glob("*.md"))
            report.delete("1.0", "end")
            if reports:
                report.insert("1.0", reports[0].read_text(encoding="utf-8"))

        ttk.Button(parent, text="Load Results / Reports", command=refresh).grid(row=1, column=1, sticky="w", padx=8, pady=6)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)

    def _build_settings(self) -> None:
        parent = self.settings_tab
        profile_var = tk.StringVar(value=str(default_threshold_profile_path()))
        ttk.Label(parent, text="Profile path").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ttk.Entry(parent, textvariable=profile_var, width=90).grid(row=0, column=1, padx=8, pady=6, sticky="ew")
        entries = [entry for entry in read_seed_registry_entries() if entry.get("family") in ALLOWED_FAMILIES]
        threshold_vars: dict[str, tk.DoubleVar] = {}
        profile = load_threshold_profile(profile_var.get() if Path(profile_var.get()).exists() else None)
        ttk.Label(parent, text="Default threshold").grid(row=1, column=0, sticky="w", padx=8)
        default_var = tk.DoubleVar(value=profile.default_threshold)
        ttk.Scale(parent, from_=0.0, to=1.0, variable=default_var, orient="horizontal").grid(row=1, column=1, sticky="ew", padx=8)
        for idx, entry in enumerate(entries, start=2):
            seed_id = str(entry["seed_id"])
            threshold_vars[seed_id] = tk.DoubleVar(value=profile.threshold_for(seed_id))
            ttk.Label(parent, text=seed_id).grid(row=idx, column=0, sticky="w", padx=8)
            ttk.Scale(parent, from_=0.0, to=1.0, variable=threshold_vars[seed_id], orient="horizontal").grid(
                row=idx, column=1, sticky="ew", padx=8
            )

        def save() -> None:
            profile.default_threshold = float(default_var.get())
            profile.signature_thresholds = {seed_id: float(var.get()) for seed_id, var in threshold_vars.items()}
            save_threshold_profile(profile, profile_var.get())
            messagebox.showinfo("Saved", profile_var.get())

        ttk.Button(parent, text="Save Threshold Profile", command=save).grid(row=len(entries) + 2, column=1, sticky="w", padx=8, pady=8)
        parent.columnconfigure(1, weight=1)

    def _result_table(self, parent: ttk.Frame, row: int) -> ttk.Treeview:
        columns = ("capture_id", "signature_id", "family", "confidence", "decision", "warnings")
        table = ttk.Treeview(parent, columns=columns, show="headings", height=12)
        for column in columns:
            table.heading(column, text=column)
            table.column(column, width=160)
        table.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        parent.rowconfigure(row, weight=1)
        return table

    def _load_table(self, table: ttk.Treeview, csv_path: Path) -> None:
        import csv

        table.delete(*table.get_children())
        if not csv_path.exists():
            return
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                table.insert(
                    "",
                    "end",
                    values=(
                        row.get("capture_id", ""),
                        row.get("signature_id", ""),
                        row.get("family", ""),
                        row.get("confidence", ""),
                        row.get("decision", ""),
                        row.get("warnings", ""),
                    ),
                )

    def _load_dataset_table(self, table: ttk.Treeview, dataset: str) -> None:
        store = ValidationStore(dataset)
        try:
            rows = [dict(row) for row in store.list_captures()]
        finally:
            store.close()
        table.delete(*table.get_children())
        for row in rows:
            table.insert("", "end", values=(row["capture_id"], row.get("seed_label", ""), "dataset", "", "", row.get("notes", "")))

    def _load_waveform_manifest_table(self, table: ttk.Treeview, manifest_path: Path) -> None:
        manifest = read_manifest(manifest_path)
        table.delete(*table.get_children())
        for row in manifest.get("captures", []):
            table.insert(
                "",
                "end",
                values=(
                    row.get("capture_id", ""),
                    row.get("stored_path", ""),
                    "waveform_set",
                    row.get("bytes", ""),
                    "imported",
                    row.get("original_path", ""),
                ),
            )

    def _load_logo(self) -> tk.PhotoImage | None:
        if not LOGO_PATH.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(LOGO_PATH))
            return image.subsample(4, 4)
        except Exception:
            return None

    def _browse_input(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename()
        if not path:
            path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _browse_dir(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _browse_save(self, var: tk.StringVar) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".db")
        if path:
            var.set(path)


def main() -> None:
    GammaApp().mainloop()


def _set_windows_app_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


if __name__ == "__main__":
    main()
