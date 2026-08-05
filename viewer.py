# viewer.py
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import database

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOG_PATH = os.path.join(DATA_DIR, "aggregator.log")
REFRESH_SIGNAL_PATH = os.path.join(DATA_DIR, "refresh.signal")
VIEW_COLUMNS = ("Title", "Company", "Source", "Location", "Salary", "Posted", "Discovered", "URL", "Applied", "Ignored", "Rejected")

def read_log_file():
    if not os.path.exists(LOG_PATH):
        return "Log file not found."
    try:
        with open(LOG_PATH, 'r', encoding='utf-8', errors='replace') as file:
            return file.read()
    except Exception as e:
        return f"Error reading log: {e}"

def refresh_data(tree, text_widget, filter_text=None, sort_state=None):
    for row in tree.get_children(): 
        tree.delete(row)

    filter_value = (filter_text or "").strip().lower()
    rows = []

    for job in database.get_recent_jobs():
        # job tuple layout: (title, company, source, location, salary, posted_at, discovered_at, url, status)
        title, company, source, location, salary, posted_at, discovered, url, status = job

        if posted_at:
            try:
                posted_at = posted_at.split("T", 1)[0]
            except Exception:
                pass

        if discovered:
            try:
                discovered_dt = discovered.replace("T", " ")
                discovered = discovered_dt[:16]
            except Exception:
                pass
        
        # Determine checkmark visual state based on recorded DB status
        applied_chk = "☑" if status == "Applied" else "☐"
        ignored_chk = "☑" if status == "Ignored" else "☐"
        rejected_chk = "☑" if status == "Rejected" else "☐"
        
        row_data = [title, company, source, location, salary, posted_at, discovered, url, applied_chk, ignored_chk, rejected_chk]
        if filter_value:
            match_text = " ".join(str(value) for value in row_data).lower()
            if filter_value not in match_text:
                continue
        rows.append(row_data)

    if sort_state and sort_state.get("column"):
        column = sort_state["column"]
        reverse = bool(sort_state.get("reverse", False))
        column_index = VIEW_COLUMNS.index(column) if column in VIEW_COLUMNS else 0
        rows.sort(key=lambda row: str(row[column_index]).lower() if column_index < len(row) else "", reverse=reverse)

    for row_data in rows:
        tree.insert('', tk.END, values=row_data)
        
    text_widget.config(state=tk.NORMAL)
    text_widget.delete(1.0, tk.END)
    log_text = read_log_file()
    if log_text:
        lines = log_text.splitlines()
        text_widget.insert(tk.END, "\n".join(reversed(lines)))
    text_widget.config(state=tk.DISABLED)

def get_refresh_marker_time():
    if not os.path.exists(REFRESH_SIGNAL_PATH):
        return None
    return os.path.getmtime(REFRESH_SIGNAL_PATH)


def run_aggregator_and_refresh(tree, text_widget, filter_text=None, sort_state=None):
    python_executable = os.path.join(os.path.dirname(__file__), "venv", "Scripts", "python.exe")
    if not os.path.exists(python_executable):
        python_executable = "python"

    subprocess.run([python_executable, os.path.join(os.path.dirname(__file__), "aggregator.py"), "Manual"], check=False)
    refresh_data(tree, text_widget, filter_text, sort_state)


def watch_for_refresh(tree, text_widget, last_seen_time, root, already_consumed=False, filter_getter=None, sort_state=None):
    latest_time = get_refresh_marker_time()
    if latest_time is not None and (last_seen_time is None or latest_time > last_seen_time):
        if not already_consumed:
            filter_text = filter_getter() if filter_getter else ""
            refresh_data(tree, text_widget, filter_text, sort_state)
            already_consumed = True
        last_seen_time = latest_time
    elif latest_time is None:
        already_consumed = False
    root.after(250, lambda: watch_for_refresh(tree, text_widget, last_seen_time, root, already_consumed, filter_getter, sort_state))


def copy_url(event, tree):
    selected_item = tree.selection()
    if not selected_item: return
    item_values = tree.item(selected_item[0], 'values')
    if len(item_values) >= 8:
        url = item_values[7] # URL is at index 7
        tree.clipboard_clear()
        tree.clipboard_append(url)
        messagebox.showinfo("URL Copied", "The job URL has been copied to your clipboard.")

def handle_single_click(event, tree, text_widget, filter_text="", sort_state=None):
    """Detects clicks on status columns and updates status without removing the row."""
    region = tree.identify("region", event.x, event.y)
    if region != "cell": return
    
    col = tree.identify_column(event.x)
    item = tree.identify_row(event.y)
    if not item: return
    
    status_map = {'#9': 'Applied', '#10': 'Ignored', '#11': 'Rejected'}
    
    if col in status_map:
        clicked_status = status_map[col]
        item_values = tree.item(item, 'values')
        url = item_values[7]

        # Toggle status: if already set to this status, reset to 'New', otherwise set to clicked status
        current_applied = item_values[8] == "☑"
        current_ignored = item_values[9] == "☑"
        current_rejected = item_values[10] == "☑"
        
        is_currently_active = (
            (clicked_status == 'Applied' and current_applied) or
            (clicked_status == 'Ignored' and current_ignored) or
            (clicked_status == 'Rejected' and current_rejected)
        )
        
        new_status = 'New' if is_currently_active else clicked_status
        
        database.update_job_status(url, new_status)
        refresh_data(tree, text_widget, filter_text, sort_state)

def sort_treeview(tree, col, reverse, sort_state=None):
    items = [(tree.set(child, col), child) for child in tree.get_children('')]
    items.sort(key=lambda x: x[0].lower() if isinstance(x[0], str) else str(x[0]), reverse=reverse)
    for index, (_, child) in enumerate(items):
        tree.move(child, '', index)

    if sort_state is not None:
        sort_state["column"] = col
        sort_state["reverse"] = reverse

    tree.heading(col, command=lambda: sort_treeview(tree, col, not reverse, sort_state))


def build_treeview(tab_db, log_text, filter_var, sort_state):
    tree = ttk.Treeview(tab_db, columns=VIEW_COLUMNS, show="headings")

    for col in VIEW_COLUMNS:
        tree.heading(col, text=col, command=lambda c=col: sort_treeview(tree, c, False, sort_state))

    tree.column("Title", width=220, anchor=tk.W)
    tree.column("Company", width=120, anchor=tk.W)
    tree.column("Source", width=100, anchor=tk.W)
    tree.column("Location", width=100, anchor=tk.W)
    tree.column("Salary", width=90, anchor=tk.W)
    tree.column("Posted", width=120, anchor=tk.W)
    tree.column("Discovered", width=130, anchor=tk.W)
    tree.column("URL", width=150, anchor=tk.W)
    tree.column("Applied", width=60, anchor=tk.CENTER)
    tree.column("Ignored", width=60, anchor=tk.CENTER)
    tree.column("Rejected", width=60, anchor=tk.CENTER)

    scrollbar = ttk.Scrollbar(tab_db, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(expand=True, fill='both')

    tree.bind("<Double-1>", lambda e: copy_url(e, tree))
    tree.bind("<ButtonRelease-1>", lambda e: handle_single_click(e, tree, log_text, filter_var.get(), sort_state))
    return tree


def main():
    root = tk.Tk()
    root.title("Local Job Board Aggregator Viewer")
    root.geometry("1200x700")

    notebook = ttk.Notebook(root)
    notebook.pack(expand=True, fill='both', padx=10, pady=10)

    tab_db = ttk.Frame(notebook)
    notebook.add(tab_db, text='Database Records')

    tab_log = ttk.Frame(notebook)
    notebook.add(tab_log, text='Execution Logs')
    log_text = scrolledtext.ScrolledText(tab_log, wrap=tk.WORD, state=tk.DISABLED)
    log_text.pack(expand=True, fill='both', padx=5, pady=5)

    filter_var = tk.StringVar()
    sort_state = {"column": None, "reverse": False}
    filter_frame = ttk.Frame(tab_db)
    filter_frame.pack(fill='x', padx=5, pady=(5, 0))
    ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
    filter_entry = ttk.Entry(filter_frame, textvariable=filter_var)
    filter_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(5, 0))
    filter_button = ttk.Button(filter_frame, text="Apply", command=lambda: refresh_data(tree, log_text, filter_var.get(), sort_state))
    filter_button.pack(side=tk.LEFT, padx=(5, 0))
    clear_button = ttk.Button(filter_frame, text="Clear", command=lambda: (filter_var.set(""), refresh_data(tree, log_text, "", sort_state)))
    clear_button.pack(side=tk.LEFT, padx=(5, 0))

    tree = build_treeview(tab_db, log_text, filter_var, sort_state)

    control_frame = ttk.Frame(root)
    control_frame.pack(fill='x', padx=10, pady=(0, 10))
    refresh_btn = ttk.Button(control_frame, text="Refresh Data", command=lambda: run_aggregator_and_refresh(tree, log_text, filter_var.get(), sort_state))
    refresh_btn.pack(side=tk.LEFT)
    hint_label = ttk.Label(control_frame, text="Double-click row to copy URL | Click status box to toggle checkmark.")
    hint_label.pack(side=tk.RIGHT)

    refresh_data(tree, log_text, "", sort_state)
    root.after(250, lambda: watch_for_refresh(tree, log_text, get_refresh_marker_time(), root, False, lambda: filter_var.get(), sort_state))
    root.mainloop()

if __name__ == "__main__":
    main()