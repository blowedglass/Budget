#!/usr/bin/env python3
"""
Personal Budget Manager
A comprehensive budget management application for couples/individuals
Features: Transaction tracking, recurring entries, visual charts, reports, save/load functionality
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import json
import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
from collections import defaultdict
import shutil

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="budget.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL,
                    person TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Recurring transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recurring_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL,
                    person TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    last_processed TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Budget categories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS budget_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT UNIQUE NOT NULL,
                    monthly_budget REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    def add_transaction(self, date, description, category, amount, trans_type, person):
        """Add a new transaction"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (date, description, category, amount, type, person)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date, description, category, amount, trans_type, person))
            conn.commit()
            return cursor.lastrowid
    
    def get_transactions(self, filters=None):
        """Get transactions with optional filters"""
        query = "SELECT * FROM transactions"
        params = []
        
        if filters:
            conditions = []
            if filters.get('start_date'):
                conditions.append("date >= ?")
                params.append(filters['start_date'])
            if filters.get('end_date'):
                conditions.append("date <= ?")
                params.append(filters['end_date'])
            if filters.get('category'):
                conditions.append("category = ?")
                params.append(filters['category'])
            if filters.get('person'):
                conditions.append("person = ?")
                params.append(filters['person'])
            if filters.get('type'):
                conditions.append("type = ?")
                params.append(filters['type'])
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY date DESC, id DESC"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def add_recurring_transaction(self, description, category, amount, trans_type, person, frequency, start_date, end_date=None):
        """Add a recurring transaction"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO recurring_transactions 
                (description, category, amount, type, person, frequency, start_date, end_date, last_processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (description, category, amount, trans_type, person, frequency, start_date, end_date, None))
            conn.commit()
            return cursor.lastrowid
    
    def get_recurring_transactions(self):
        """Get all active recurring transactions"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recurring_transactions WHERE active = 1 ORDER BY id")
            return cursor.fetchall()
    
    def process_recurring_transactions(self):
        """Process recurring transactions that are due"""
        recurring = self.get_recurring_transactions()
        processed_count = 0
        
        for rec in recurring:
            _, description, category, amount, trans_type, person, frequency, start_date, end_date, last_processed, active, _ = rec
            
            # Calculate next due date
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            last_processed_dt = datetime.strptime(last_processed, '%Y-%m-%d') if last_processed else start_dt - timedelta(days=1)
            
            next_due = self._calculate_next_due_date(last_processed_dt, frequency)
            today = datetime.now().date()
            
            # Check if due and within end date
            if next_due <= today:
                if not end_date or datetime.strptime(end_date, '%Y-%m-%d').date() >= today:
                    # Add transaction
                    self.add_transaction(
                        next_due.strftime('%Y-%m-%d'),
                        f"{description} (Auto)",
                        category,
                        amount,
                        trans_type,
                        person
                    )
                    
                    # Update last processed date
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE recurring_transactions 
                            SET last_processed = ? 
                            WHERE id = ?
                        """, (next_due.strftime('%Y-%m-%d'), rec[0]))
                        conn.commit()
                    
                    processed_count += 1
        
        return processed_count
    
    def _calculate_next_due_date(self, last_date, frequency):
        """Calculate next due date based on frequency"""
        if frequency == "daily":
            return last_date.date() + timedelta(days=1)
        elif frequency == "weekly":
            return last_date.date() + timedelta(weeks=1)
        elif frequency == "bi-weekly":
            return last_date.date() + timedelta(weeks=2)
        elif frequency == "monthly":
            # Add one month
            if last_date.month == 12:
                return last_date.replace(year=last_date.year + 1, month=1).date()
            else:
                return last_date.replace(month=last_date.month + 1).date()
        elif frequency == "yearly":
            return last_date.replace(year=last_date.year + 1).date()
        else:
            return last_date.date() + timedelta(days=1)

class SaveLoadManager:
    """Handles save/load functionality for sharing between devices"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def export_data(self, filepath):
        """Export all data to a JSON file"""
        try:
            data = {
                'transactions': self.db_manager.get_transactions(),
                'recurring_transactions': self.db_manager.get_recurring_transactions(),
                'export_date': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            return True
        except Exception as e:
            print(f"Export error: {e}")
            return False
    
    def import_data(self, filepath, merge=True):
        """Import data from a JSON file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            if not merge:
                # Clear existing data
                with sqlite3.connect(self.db_manager.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM transactions")
                    cursor.execute("DELETE FROM recurring_transactions")
                    conn.commit()
            
            # Import transactions
            for trans in data.get('transactions', []):
                # Skip if already exists (for merge mode)
                if merge:
                    existing = self.db_manager.get_transactions({
                        'start_date': trans[1],
                        'end_date': trans[1]
                    })
                    if any(t[2] == trans[2] and t[4] == trans[4] and t[1] == trans[1] for t in existing):
                        continue
                
                self.db_manager.add_transaction(
                    trans[1], trans[2], trans[3], trans[4], trans[5], trans[6]
                )
            
            # Import recurring transactions
            for rec in data.get('recurring_transactions', []):
                if merge:
                    # Check if similar recurring transaction exists
                    existing_rec = self.db_manager.get_recurring_transactions()
                    if any(r[1] == rec[1] and r[4] == rec[4] and r[6] == rec[6] for r in existing_rec):
                        continue
                
                self.db_manager.add_recurring_transaction(
                    rec[1], rec[2], rec[3], rec[4], rec[5], rec[6], rec[7], rec[8]
                )
            
            return True
        except Exception as e:
            print(f"Import error: {e}")
            return False

class BudgetApp:
    """Main application class"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Personal Budget Manager - CM™)
        self.root.geometry("1200x800")
        
        # Initialize managers
        self.db_manager = DatabaseManager()
        self.save_load_manager = SaveLoadManager(self.db_manager)
        
        # Process recurring transactions on startup
        self.db_manager.process_recurring_transactions()
        
        # Create GUI
        self.create_gui()
        
        # Refresh data
        self.refresh_transactions()
        self.update_chart()
        self.update_summary()
    
    def create_gui(self):
        """Create the main GUI"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_main_tab()
        self.create_recurring_tab()
        self.create_reports_tab()
        self.create_settings_tab()
    
    def create_main_tab(self):
        """Create main transactions tab"""
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text="Transactions")
        
        # Top frame for entry and controls
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Entry section
        entry_frame = ttk.LabelFrame(top_frame, text="Add New Transaction")
        entry_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Entry fields
        ttk.Label(entry_frame, text="Date:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.date_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        ttk.Entry(entry_frame, textvariable=self.date_var, width=12).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Description:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.desc_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.desc_var, width=25).grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Category:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.cat_var = tk.StringVar()
        cat_combo = ttk.Combobox(entry_frame, textvariable=self.cat_var, width=15)
        cat_combo['values'] = ('Food', 'Transportation', 'Entertainment', 'Utilities', 'Rent', 'Income', 'Shopping', 'Healthcare', 'Other')
        cat_combo.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Amount:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        self.amount_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.amount_var, width=12).grid(row=1, column=3, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Type:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.type_var = tk.StringVar()
        type_combo = ttk.Combobox(entry_frame, textvariable=self.type_var, width=12)
        type_combo['values'] = ('Income', 'Expense')
        type_combo.grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Person:").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        self.person_var = tk.StringVar()
        person_combo = ttk.Combobox(entry_frame, textvariable=self.person_var, width=12)
        person_combo['values'] = ('Person 1', 'Person 2', 'Both')
        person_combo.grid(row=2, column=3, padx=5, pady=2)
        
        ttk.Button(entry_frame, text="Add Transaction", command=self.add_transaction).grid(row=2, column=4, padx=10, pady=2)
        
        # Filter section
        filter_frame = ttk.LabelFrame(top_frame, text="Filters")
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Filter controls
        ttk.Label(filter_frame, text="Start Date:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.filter_start_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.filter_start_var, width=12).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(filter_frame, text="End Date:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.filter_end_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.filter_end_var, width=12).grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(filter_frame, text="Category:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=2)
        self.filter_cat_var = tk.StringVar()
        filter_cat_combo = ttk.Combobox(filter_frame, textvariable=self.filter_cat_var, width=15)
        filter_cat_combo['values'] = ('All', 'Food', 'Transportation', 'Entertainment', 'Utilities', 'Rent', 'Income', 'Shopping', 'Healthcare', 'Other')
        filter_cat_combo.set('All')
        filter_cat_combo.grid(row=0, column=5, padx=5, pady=2)
        
        ttk.Button(filter_frame, text="Apply Filters", command=self.apply_filters).grid(row=0, column=6, padx=10, pady=2)
        ttk.Button(filter_frame, text="Clear Filters", command=self.clear_filters).grid(row=0, column=7, padx=5, pady=2)
        
        # Bottom frame for table and chart
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left frame for transactions table
        left_frame = ttk.Frame(bottom_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Transactions table
        columns = ('ID', 'Date', 'Description', 'Category', 'Amount', 'Type', 'Person')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.tree.heading(col, text=col)
            if col == 'ID':
                self.tree.column(col, width=50)
            elif col == 'Date':
                self.tree.column(col, width=100)
            elif col == 'Amount':
                self.tree.column(col, width=100)
            else:
                self.tree.column(col, width=120)
        
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Right frame for chart and summary
        right_frame = ttk.Frame(bottom_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        
        # Summary frame
        summary_frame = ttk.LabelFrame(right_frame, text="Summary")
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.summary_text = tk.Text(summary_frame, height=8, width=30)
        self.summary_text.pack(padx=5, pady=5)
        
        # Chart frame
        chart_frame = ttk.LabelFrame(right_frame, text="Balance Over Time")
        chart_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_recurring_tab(self):
        """Create recurring transactions tab"""
        recurring_frame = ttk.Frame(self.notebook)
        self.notebook.add(recurring_frame, text="Recurring")
        
        # Entry section
        entry_frame = ttk.LabelFrame(recurring_frame, text="Add Recurring Transaction")
        entry_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Recurring entry fields
        ttk.Label(entry_frame, text="Description:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.rec_desc_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.rec_desc_var, width=25).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Category:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.rec_cat_var = tk.StringVar()
        rec_cat_combo = ttk.Combobox(entry_frame, textvariable=self.rec_cat_var, width=15)
        rec_cat_combo['values'] = ('Food', 'Transportation', 'Entertainment', 'Utilities', 'Rent', 'Income', 'Shopping', 'Healthcare', 'Other')
        rec_cat_combo.grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Amount:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.rec_amount_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.rec_amount_var, width=12).grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Type:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        self.rec_type_var = tk.StringVar()
        rec_type_combo = ttk.Combobox(entry_frame, textvariable=self.rec_type_var, width=12)
        rec_type_combo['values'] = ('Income', 'Expense')
        rec_type_combo.grid(row=1, column=3, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Person:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.rec_person_var = tk.StringVar()
        rec_person_combo = ttk.Combobox(entry_frame, textvariable=self.rec_person_var, width=12)
        rec_person_combo['values'] = ('Person 1', 'Person 2', 'Both')
        rec_person_combo.grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Frequency:").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        self.rec_freq_var = tk.StringVar()
        freq_combo = ttk.Combobox(entry_frame, textvariable=self.rec_freq_var, width=12)
        freq_combo['values'] = ('daily', 'weekly', 'bi-weekly', 'monthly', 'yearly')
        freq_combo.grid(row=2, column=3, padx=5, pady=2)
        
        ttk.Label(entry_frame, text="Start Date:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.rec_start_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        ttk.Entry(entry_frame, textvariable=self.rec_start_var, width=12).grid(row=3, column=1, padx=5, pady=2)
        
        ttk.Button(entry_frame, text="Add Recurring", command=self.add_recurring_transaction).grid(row=3, column=3, padx=10, pady=2)
        
        # Recurring transactions list
        list_frame = ttk.LabelFrame(recurring_frame, text="Recurring Transactions")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        rec_columns = ('ID', 'Description', 'Category', 'Amount', 'Type', 'Person', 'Frequency', 'Start Date')
        self.rec_tree = ttk.Treeview(list_frame, columns=rec_columns, show='headings')
        
        for col in rec_columns:
            self.rec_tree.heading(col, text=col)
            if col == 'ID':
                self.rec_tree.column(col, width=50)
            else:
                self.rec_tree.column(col, width=120)
        
        rec_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=rec_scrollbar.set)
        
        self.rec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rec_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Refresh recurring transactions
        self.refresh_recurring()
    
    def create_reports_tab(self):
        """Create reports tab"""
        reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(reports_frame, text="Reports")
        
        # Report controls
        control_frame = ttk.Frame(reports_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Monthly Report", command=self.generate_monthly_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Category Report", command=self.generate_category_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Person Report", command=self.generate_person_report).pack(side=tk.LEFT, padx=5)
        
        # Report display
        self.report_text = tk.Text(reports_frame, wrap=tk.WORD)
        report_scrollbar = ttk.Scrollbar(reports_frame, orient=tk.VERTICAL, command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=report_scrollbar.set)
        
        self.report_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        report_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
    
    def create_settings_tab(self):
        """Create settings and save/load tab"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")
        
        # Save/Load section
        save_frame = ttk.LabelFrame(settings_frame, text="Save & Load Data")
        save_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(save_frame, text="Export Data", command=self.export_data).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(save_frame, text="Import Data (Merge)", command=lambda: self.import_data(True)).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(save_frame, text="Import Data (Replace)", command=lambda: self.import_data(False)).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Database info
        info_frame = ttk.LabelFrame(settings_frame, text="Database Information")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.info_text = tk.Text(info_frame, height=10, wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.update_info()
    
    def add_transaction(self):
        """Add a new transaction"""
        try:
            date = self.date_var.get()
            description = self.desc_var.get().strip()
            category = self.cat_var.get().strip()
            amount = float(self.amount_var.get())
            trans_type = self.type_var.get()
            person = self.person_var.get()
            
            if not all([date, description, category, trans_type, person]):
                messagebox.showerror("Error", "Please fill all fields")
                return
            
            self.db_manager.add_transaction(date, description, category, amount, trans_type, person)
            
            # Clear fields
            self.desc_var.set("")
            self.amount_var.set("")
            self.date_var.set(datetime.now().strftime('%Y-%m-%d'))
            
            # Refresh displays
            self.refresh_transactions()
            self.update_chart()
            self.update_summary()
            
            messagebox.showinfo("Success", "Transaction added successfully!")
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid amount")
        except Exception as e:
            messagebox.showerror("Error", f"Error adding transaction: {str(e)}")
    
    def add_recurring_transaction(self):
        """Add a new recurring transaction"""
        try:
            description = self.rec_desc_var.get().strip()
            category = self.rec_cat_var.get().strip()
            amount = float(self.rec_amount_var.get())
            trans_type = self.rec_type_var.get()
            person = self.rec_person_var.get()
            frequency = self.rec_freq_var.get()
            start_date = self.rec_start_var.get()
            
            if not all([description, category, trans_type, person, frequency, start_date]):
                messagebox.showerror("Error", "Please fill all fields")
                return
            
            self.db_manager.add_recurring_transaction(
                description, category, amount, trans_type, person, frequency, start_date
            )
            
            # Clear fields
            self.rec_desc_var.set("")
            self.rec_amount_var.set("")
            self.rec_start_var.set(datetime.now().strftime('%Y-%m-%d'))
            
            self.refresh_recurring()
            messagebox.showinfo("Success", "Recurring transaction added successfully!")
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid amount")
        except Exception as e:
            messagebox.showerror("Error", f"Error adding recurring transaction: {str(e)}")
    
    def refresh_transactions(self):
        """Refresh the transactions table"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Get current filters
        filters = {}
        if self.filter_start_var.get():
            filters['start_date'] = self.filter_start_var.get()
        if self.filter_end_var.get():
            filters['end_date'] = self.filter_end_var.get()
        if self.filter_cat_var.get() and self.filter_cat_var.get() != 'All':
            filters['category'] = self.filter_cat_var.get()
        
        transactions = self.db_manager.get_transactions(filters)
        
        for trans in transactions:
            # Format amount with proper sign and color
            amount = trans[4]
            if trans[5] == 'Expense':
                amount_str = f"-${abs(amount):.2f}"
                tags = ('expense',)
            else:
                amount_str = f"+${amount:.2f}"
                tags = ('income',)
            
            self.tree.insert('', 'end', values=(
                trans[0], trans[1], trans[2], trans[3], 
                amount_str, trans[5], trans[6]
            ), tags=tags)
        
        # Configure tags for coloring
        self.tree.tag_configure('expense', foreground='red')
        self.tree.tag_configure('income', foreground='green')
    
    def refresh_recurring(self):
        """Refresh the recurring transactions table"""
        for item in self.rec_tree.get_children():
            self.rec_tree.delete(item)
        
        recurring = self.db_manager.get_recurring_transactions()
        for rec in recurring:
            amount_str = f"${rec[3]:.2f}" if rec[4] == 'Income' else f"-${rec[3]:.2f}"
            self.rec_tree.insert('', 'end', values=(
                rec[0], rec[1], rec[2], amount_str, rec[4], rec[5], rec[6], rec[7]
            ))
    
    def apply_filters(self):
        """Apply current filters to transaction view"""
        self.refresh_transactions()
        self.update_chart()
        self.update_summary()
    
    def clear_filters(self):
        """Clear all filters"""
        self.filter_start_var.set("")
        self.filter_end_var.set("")
        self.filter_cat_var.set("All")
        self.refresh_transactions()
        self.update_chart()
        self.update_summary()
    
    def update_chart(self):
        """Update the balance over time chart"""
        # Get transactions for chart
        filters = {}
        if self.filter_start_var.get():
            filters['start_date'] = self.filter_start_var.get()
        if self.filter_end_var.get():
            filters['end_date'] = self.filter_end_var.get()
        
        transactions = self.db_manager.get_transactions(filters)
        
        # Calculate running balance
        balance_data = defaultdict(float)
        dates = []
        balances = []
        
        # Sort by date
        transactions.sort(key=lambda x: x[1])
        
        running_balance = 0
        for trans in transactions:
            date = trans[1]
            amount = trans[4] if trans[5] == 'Income' else -trans[4]
            running_balance += amount
            
            dates.append(datetime.strptime(date, '%Y-%m-%d'))
            balances.append(running_balance)
        
        # Clear and plot
        self.ax.clear()
        if dates and balances:
            self.ax.plot(dates, balances, marker='o', linewidth=2)
            self.ax.set_title('Balance Over Time')
            self.ax.set_xlabel('Date')
            self.ax.set_ylabel('Balance ($)')
            self.ax.grid(True, alpha=0.3)
            
            # Color coding
            if balances[-1] >= 0:
                self.ax.plot(dates, balances, color='green', marker='o', linewidth=2)
            else:
                self.ax.plot(dates, balances, color='red', marker='o', linewidth=2)
        else:
            self.ax.text(0.5, 0.5, 'No data to display', ha='center', va='center', transform=self.ax.transAxes)
        
        self.fig.autofmt_xdate()
        self.canvas.draw()
    
    def update_summary(self):
        """Update the summary text"""
        filters = {}
        if self.filter_start_var.get():
            filters['start_date'] = self.filter_start_var.get()
        if self.filter_end_var.get():
            filters['end_date'] = self.filter_end_var.get()
        
        transactions = self.db_manager.get_transactions(filters)
        
        total_income = sum(t[4] for t in transactions if t[5] == 'Income')
        total_expenses = sum(t[4] for t in transactions if t[5] == 'Expense')
        net_balance = total_income - total_expenses
        
        # Category breakdown
        categories = defaultdict(float)
        for trans in transactions:
            if trans[5] == 'Expense':
                categories[trans[3]] += trans[4]
        
        # Person breakdown
        person_stats = defaultdict(lambda: {'income': 0, 'expenses': 0})
        for trans in transactions:
            person = trans[6]
            if trans[5] == 'Income':
                person_stats[person]['income'] += trans[4]
            else:
                person_stats[person]['expenses'] += trans[4]
        
        summary = f"""FINANCIAL SUMMARY
{'='*30}

Total Income: ${total_income:.2f}
Total Expenses: ${total_expenses:.2f}
Net Balance: ${net_balance:.2f}

TOP EXPENSE CATEGORIES:
"""
        
        sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
        for cat, amount in sorted_categories:
            summary += f"{cat}: ${amount:.2f}\n"
        
        summary += f"\nPERSON BREAKDOWN:\n"
        for person, stats in person_stats.items():
            net = stats['income'] - stats['expenses']
            summary += f"{person}:\n  Income: ${stats['income']:.2f}\n  Expenses: ${stats['expenses']:.2f}\n  Net: ${net:.2f}\n\n"
        
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(1.0, summary)
    
    def generate_monthly_report(self):
        """Generate monthly spending report"""
        now = datetime.now()
        start_date = now.replace(day=1).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        
        filters = {'start_date': start_date, 'end_date': end_date}
        transactions = self.db_manager.get_transactions(filters)
        
        total_income = sum(t[4] for t in transactions if t[5] == 'Income')
        total_expenses = sum(t[4] for t in transactions if t[5] == 'Expense')
        
        categories = defaultdict(float)
        for trans in transactions:
            if trans[5] == 'Expense':
                categories[trans[3]] += trans[4]
        
        report = f"""MONTHLY REPORT - {now.strftime('%B %Y')}
{'='*50}

SUMMARY:
Total Income: ${total_income:.2f}
Total Expenses: ${total_expenses:.2f}
Net Savings: ${total_income - total_expenses:.2f}

EXPENSES BY CATEGORY:
"""
        
        sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        for cat, amount in sorted_categories:
            percentage = (amount / total_expenses * 100) if total_expenses > 0 else 0
            report += f"{cat}: ${amount:.2f} ({percentage:.1f}%)\n"
        
        report += f"\nTRANSACTION COUNT: {len(transactions)}\n"
        report += f"AVERAGE TRANSACTION: ${(total_income + total_expenses) / len(transactions):.2f}\n" if transactions else ""
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(1.0, report)
    
    def generate_category_report(self):
        """Generate category spending report"""
        transactions = self.db_manager.get_transactions()
        
        categories = defaultdict(lambda: {'count': 0, 'total': 0, 'avg': 0})
        
        for trans in transactions:
            cat = trans[3]
            amount = trans[4]
            categories[cat]['count'] += 1
            categories[cat]['total'] += amount
        
        for cat in categories:
            categories[cat]['avg'] = categories[cat]['total'] / categories[cat]['count']
        
        report = f"""CATEGORY ANALYSIS REPORT
{'='*50}

"""
        
        sorted_categories = sorted(categories.items(), key=lambda x: x[1]['total'], reverse=True)
        for cat, stats in sorted_categories:
            report += f"{cat.upper()}:\n"
            report += f"  Total Spent: ${stats['total']:.2f}\n"
            report += f"  Transaction Count: {stats['count']}\n"
            report += f"  Average per Transaction: ${stats['avg']:.2f}\n\n"
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(1.0, report)
    
    def generate_person_report(self):
        """Generate person-based spending report"""
        transactions = self.db_manager.get_transactions()
        
        person_stats = defaultdict(lambda: {
            'income': 0, 'expenses': 0, 'transactions': 0,
            'categories': defaultdict(float)
        })
        
        for trans in transactions:
            person = trans[6]
            amount = trans[4]
            category = trans[3]
            trans_type = trans[5]
            
            person_stats[person]['transactions'] += 1
            if trans_type == 'Income':
                person_stats[person]['income'] += amount
            else:
                person_stats[person]['expenses'] += amount
                person_stats[person]['categories'][category] += amount
        
        report = f"""PERSON-BASED SPENDING REPORT
{'='*50}

"""
        
        for person, stats in person_stats.items():
            net = stats['income'] - stats['expenses']
            report += f"{person.upper()}:\n"
            report += f"  Total Income: ${stats['income']:.2f}\n"
            report += f"  Total Expenses: ${stats['expenses']:.2f}\n"
            report += f"  Net Balance: ${net:.2f}\n"
            report += f"  Total Transactions: {stats['transactions']}\n"
            
            if stats['categories']:
                report += f"  Top Categories:\n"
                top_cats = sorted(stats['categories'].items(), key=lambda x: x[1], reverse=True)[:3]
                for cat, amount in top_cats:
                    report += f"    {cat}: ${amount:.2f}\n"
            report += "\n"
        
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(1.0, report)
    
    def export_data(self):
        """Export data to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Export Budget Data"
        )
        
        if filename:
            if self.save_load_manager.export_data(filename):
                messagebox.showinfo("Success", f"Data exported to {filename}")
            else:
                messagebox.showerror("Error", "Failed to export data")
    
    def import_data(self, merge=True):
        """Import data from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Import Budget Data"
        )
        
        if filename:
            mode = "merge" if merge else "replace"
            confirm = messagebox.askyesno(
                "Confirm Import", 
                f"This will {mode} your current data. Continue?"
            )
            
            if confirm:
                if self.save_load_manager.import_data(filename, merge):
                    self.refresh_transactions()
                    self.refresh_recurring()
                    self.update_chart()
                    self.update_summary()
                    self.update_info()
                    messagebox.showinfo("Success", "Data imported successfully!")
                else:
                    messagebox.showerror("Error", "Failed to import data")
    
    def update_info(self):
        """Update database information"""
        transactions = self.db_manager.get_transactions()
        recurring = self.db_manager.get_recurring_transactions()
        
        total_income = sum(t[4] for t in transactions if t[5] == 'Income')
        total_expenses = sum(t[4] for t in transactions if t[5] == 'Expense')
        
        info = f"""DATABASE INFORMATION
{'='*30}

Database Path: {self.db_manager.db_path}
Total Transactions: {len(transactions)}
Recurring Transactions: {len(recurring)}

All-Time Summary:
Total Income: ${total_income:.2f}
Total Expenses: ${total_expenses:.2f}
Net Balance: ${total_income - total_expenses:.2f}

Recent Activity:
"""
        
        recent_transactions = transactions[:5]  # Last 5 transactions
        for trans in recent_transactions:
            date = trans[1]
            desc = trans[2][:20] + "..." if len(trans[2]) > 20 else trans[2]
            amount = trans[4]
            info += f"{date}: {desc} - ${amount:.2f}\n"
        
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, info)

def main():
    """Main function to run the application"""
    try:
        # Check for required modules
        import matplotlib
        import pandas
        print("All required modules found!")
    except ImportError as e:
        print(f"Missing required module: {e}")
        print("Please install required packages:")
        print("pip install matplotlib pandas")
        return
    
    root = tk.Tk()
    app = BudgetApp(root)
    
    # Process recurring transactions on startup
    processed = app.db_manager.process_recurring_transactions()
    if processed > 0:
        messagebox.showinfo("Recurring Transactions", 
                           f"Processed {processed} recurring transactions")
    
    root.mainloop()

if __name__ == "__main__":
    main()