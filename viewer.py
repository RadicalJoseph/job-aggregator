# viewer.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import database

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOG_PATH = os.path.join(DATA_DIR, "aggregator.log")

def read_log_file():
    if not os.path.exists(LOG_PATH): return "Log file not found."
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as file: return file.read()
    except Exception as e: return f"Error reading log: {e}"

def refresh_data(tree, text_widget):
    for row in tree.get_children(): tree.delete(row)
    for job in database.get_recent_jobs():
        # Append empty checkbox symbols to the standard database row
        row_data = list(job) + ["☐", "☐", "☐"]
        tree.insert('', tk.END, values=row_data)
        
    text_widget.config(state=tk.NORMAL)
    text_widget.delete(1.0, tk.END)
    text_widget.insert(tk.END, read_log_file())
    text_widget.config(state=tk.DISABLED)

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
    """Detects clicks on interactive checkbox columns and updates job status."""
    region = tree.identify("region", event.x, event.y)
    if region != "cell": return
    
    col = tree.identify_column(event.x)
    item = tree.identify_row(event.y)
    if not item: return
    
    status_map = {'#8': 'Applied', '#9': 'Ignored', '#10': 'Rejected'}
    
    if col in status_map:
        new_status = status_map[col]
        item_values = tree.item(item, 'values')
        url = item_values[6] 
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

    # Reconfigured schema columns including interactive endpoints
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
    
    # Event bindings for UX logic
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
    hint_label = ttk.Label(control_frame, text="Double-click row to copy URL | Single-click status box to filter job from future views.")
    hint_label.pack(side=tk.RIGHT)

    refresh_data(tree, log_text)
    root.mainloop()

if __name__ == "__main__":
    main()