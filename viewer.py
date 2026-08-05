# viewer.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import database

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOG_PATH = os.path.join(DATA_DIR, "aggregator.log")
REFRESH_SIGNAL_PATH = os.path.join(DATA_DIR, "refresh.signal")

def read_log_file():
    if not os.path.exists(LOG_PATH): return "Log file not found."
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as file: return file.read()
    except Exception as e: return f"Error reading log: {e}"

def refresh_data(tree, text_widget):
    for row in tree.get_children(): 
        tree.delete(row)

    for job in database.get_recent_jobs():
        # job tuple layout: (title, company, source, location, salary, discovered_at, url, status)
        title, company, source, location, salary, discovered, url, status = job
        
        # Determine checkmark visual state based on recorded DB status
        applied_chk = "☑" if status == "Applied" else "☐"
        ignored_chk = "☑" if status == "Ignored" else "☐"
        rejected_chk = "☑" if status == "Rejected" else "☐"
        
        row_data = [title, company, source, location, salary, discovered, url, applied_chk, ignored_chk, rejected_chk]
        tree.insert('', tk.END, values=row_data)
        
    text_widget.config(state=tk.NORMAL)
    text_widget.delete(1.0, tk.END)
    text_widget.insert(tk.END, read_log_file())
    text_widget.config(state=tk.DISABLED)

def get_refresh_marker_time():
    if not os.path.exists(REFRESH_SIGNAL_PATH):
        return None
    return os.path.getmtime(REFRESH_SIGNAL_PATH)


def watch_for_refresh(tree, text_widget, last_seen_time, root, already_consumed=False):
    latest_time = get_refresh_marker_time()
    if latest_time is not None and (last_seen_time is None or latest_time > last_seen_time):
        if not already_consumed:
            refresh_data(tree, text_widget)
            already_consumed = True
        last_seen_time = latest_time
    elif latest_time is None:
        already_consumed = False
    root.after(250, lambda: watch_for_refresh(tree, text_widget, last_seen_time, root, already_consumed))


def copy_url(event, tree):
    selected_item = tree.selection()
    if not selected_item: return
    item_values = tree.item(selected_item[0], 'values')
    if len(item_values) >= 7:
        url = item_values[6] # URL is at index 6
        tree.clipboard_clear()
        tree.clipboard_append(url)
        messagebox.showinfo("URL Copied", "The job URL has been copied to your clipboard.")

def handle_single_click(event, tree, text_widget):
    """Detects clicks on status columns and updates status without removing the row."""
    region = tree.identify("region", event.x, event.y)
    if region != "cell": return
    
    col = tree.identify_column(event.x)
    item = tree.identify_row(event.y)
    if not item: return
    
    status_map = {'#8': 'Applied', '#9': 'Ignored', '#10': 'Rejected'}
    
    if col in status_map:
        clicked_status = status_map[col]
        item_values = tree.item(item, 'values')
        url = item_values[6]
        
        # Toggle status: if already set to this status, reset to 'New', otherwise set to clicked status
        current_applied = item_values[7] == "☑"
        current_ignored = item_values[8] == "☑"
        current_rejected = item_values[9] == "☑"
        
        is_currently_active = (
            (clicked_status == 'Applied' and current_applied) or
            (clicked_status == 'Ignored' and current_ignored) or
            (clicked_status == 'Rejected' and current_rejected)
        )
        
        new_status = 'New' if is_currently_active else clicked_status
        
        database.update_job_status(url, new_status)
        refresh_data(tree, text_widget)

def main():
    root = tk.Tk()
    root.title("Local Job Board Aggregator Viewer")
    root.geometry("1200x700")

    notebook = ttk.Notebook(root)
    notebook.pack(expand=True, fill='both', padx=10, pady=10)

    tab_db = ttk.Frame(notebook)
    notebook.add(tab_db, text='Database Records')

    columns = ("Title", "Company", "Source", "Location", "Salary", "Discovered", "URL", "Applied", "Ignored", "Rejected")
    tree = ttk.Treeview(tab_db, columns=columns, show="headings")

    for col in columns:
        tree.heading(col, text=col)
    
    tree.column("Title", width=220, anchor=tk.W)
    tree.column("Company", width=120, anchor=tk.W)
    tree.column("Source", width=100, anchor=tk.W)
    tree.column("Location", width=100, anchor=tk.W)
    tree.column("Salary", width=90, anchor=tk.W)
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
    tree.bind("<ButtonRelease-1>", lambda e: handle_single_click(e, tree, log_text))

    tab_log = ttk.Frame(notebook)
    notebook.add(tab_log, text='Execution Logs')
    log_text = scrolledtext.ScrolledText(tab_log, wrap=tk.WORD, state=tk.DISABLED)
    log_text.pack(expand=True, fill='both', padx=5, pady=5)

    control_frame = ttk.Frame(root)
    control_frame.pack(fill='x', padx=10, pady=(0, 10))
    refresh_btn = ttk.Button(control_frame, text="Refresh Data", command=lambda: refresh_data(tree, log_text))
    refresh_btn.pack(side=tk.LEFT)
    hint_label = ttk.Label(control_frame, text="Double-click row to copy URL | Click status box to toggle checkmark.")
    hint_label.pack(side=tk.RIGHT)

    refresh_data(tree, log_text)
    root.after(250, lambda: watch_for_refresh(tree, log_text, get_refresh_marker_time(), root, False))
    root.mainloop()

if __name__ == "__main__":
    main()