# viewer.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import sqlite3
import os

# Define relative paths to local runtime data
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")
LOG_PATH = os.path.join(DATA_DIR, "aggregator.log")

def fetch_db_records():
    """Retrieve all job records from the local SQLite database."""
    if not os.path.exists(DB_PATH):
        return []
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Query specific columns to match the Treeview layout
        cursor.execute("""
            SELECT title, company, source, location, discovered_at, url 
            FROM jobs 
            ORDER BY discovered_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"Database error: {e}")
        return []

def read_log_file():
    """Read the raw text contents of the aggregator execution log."""
    if not os.path.exists(LOG_PATH):
        return "Log file not found. Ensure the aggregator has run at least once."
    
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        return f"Error reading log: {e}"

def refresh_data(tree, text_widget):
    """Clear and reload both the database Treeview and the log text widget."""
    # 1. Clear existing treeview rows
    for row in tree.get_children():
        tree.delete(row)
        
    # 2. Populate treeview with fresh database records
    for job in fetch_db_records():
        tree.insert('', tk.END, values=job)
        
    # 3. Update log text area
    text_widget.config(state=tk.NORMAL)
    text_widget.delete(1.0, tk.END)
    text_widget.insert(tk.END, read_log_file())
    text_widget.config(state=tk.DISABLED)

def copy_url(event, tree):
    """Copy the selected job's URL to the system clipboard on double-click."""
    selected_item = tree.selection()
    if not selected_item:
        return
    
    # URL is located at index 5 of the values tuple
    item_values = tree.item(selected_item[0], 'values')
    if len(item_values) >= 6:
        url = item_values[5]
        tree.clipboard_clear()
        tree.clipboard_append(url)
        messagebox.showinfo("URL Copied", "The job URL has been copied to your clipboard.")

def main():
    # Initialize main window
    root = tk.Tk()
    root.title("Local Job Board Aggregator Viewer")
    root.geometry("1100x650")

    # Create primary tab control unit
    notebook = ttk.Notebook(root)
    notebook.pack(expand=True, fill='both', padx=10, pady=10)

    # --- TAB 1: Database Viewer ---
    tab_db = ttk.Frame(notebook)
    notebook.add(tab_db, text='Database Records')

    # Define and configure columns for the hierarchical Treeview
    columns = ("Title", "Company", "Source", "Location", "Discovered", "URL")
    tree = ttk.Treeview(tab_db, columns=columns, show="headings")

    # Format header text and establish column widths
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=120, anchor=tk.W)
    
    # Expand specific columns for better readability
    tree.column("Title", width=250)
    tree.column("URL", width=300)
    tree.column("Discovered", width=150)

    # Attach vertical scrollbar to the Treeview
    scrollbar = ttk.Scrollbar(tab_db, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(expand=True, fill='both')
    
    # Bind the double-click event listener to the copy function
    tree.bind("<Double-1>", lambda event: copy_url(event, tree))

    # --- TAB 2: Log Viewer ---
    tab_log = ttk.Frame(notebook)
    notebook.add(tab_log, text='Execution Logs')

    # Configure read-only ScrolledText widget for log output
    log_text = scrolledtext.ScrolledText(tab_log, wrap=tk.WORD, state=tk.DISABLED)
    log_text.pack(expand=True, fill='both', padx=5, pady=5)

    # --- Global Controls ---
    control_frame = ttk.Frame(root)
    control_frame.pack(fill='x', padx=10, pady=(0, 10))

    refresh_btn = ttk.Button(control_frame, text="Refresh Data", command=lambda: refresh_data(tree, log_text))
    refresh_btn.pack(side=tk.LEFT)

    hint_label = ttk.Label(control_frame, text="Action: Double-click any row in the Database Records tab to copy the URL.")
    hint_label.pack(side=tk.RIGHT)

    # Trigger initial data load upon startup
    refresh_data(tree, log_text)

    # Execute main event loop
    root.mainloop()

if __name__ == "__main__":
    main()