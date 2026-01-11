import pandas as pd
import os
import streamlit as st

# Constants
LOCAL_FILE_PATH = r"C:\Users\Mani Raju\.gemini\antigravity\scratch\GpayTracker.xlsx"

class DataService:
    def __init__(self):
        # In future, check st.secrets or env vars for GSheets toggle
        self.use_gsheets = True 
        self.file_path = LOCAL_FILE_PATH
        self.xl = None
        self.all_sheet_names = []
        self._load_metadata()

    def _load_metadata(self):
        """Loads the workbook metadata (sheet names)"""
        try:
            if self.use_gsheets:
                import gspread
                from google.oauth2.service_account import Credentials
                
                # Load credentials from st.secrets or local file
                # Expects st.secrets["gcp_service_account"] or a path in secrets
                creds_dict = st.secrets["gcp_service_account"]
                scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
                creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                client = gspread.authorize(creds)
                
                # Open by ID (preferred) or Name
                sheet_id = st.secrets["G_SHEET_ID"]
                self.xl = client.open_by_key(sheet_id)
                
                # Get all worksheets
                self.all_sheet_names = [ws.title for ws in self.xl.worksheets()]
                
            else:
                if not os.path.exists(self.file_path):
                    raise FileNotFoundError(f"File not found: {self.file_path}")
                
                self.xl = pd.ExcelFile(self.file_path)
                self.all_sheet_names = self.xl.sheet_names
                
        except Exception as e:
            st.error(f"Error initializing data service: {e}")
            self.all_sheet_names = []
            
    def get_available_years(self):
        """Extracts years from sheet names (Expected format: 'Month YYYY')"""
        years = set()
        for name in self.all_sheet_names:
            parts = name.split()
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
                years.add(parts[1])
        return sorted(list(years))

    def get_months_for_year(self, year):
        """Returns list of months available for a given year"""
        months = []
        # Define month order for sorting
        month_order = {
            "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
            "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
        }
        
        found_months = []
        for name in self.all_sheet_names:
            parts = name.split()
            if len(parts) == 2 and parts[1] == str(year):
                found_months.append(parts[0])
                
        # Sort months chronologically
        try:
            found_months.sort(key=lambda x: month_order.get(x, 99))
        except:
            pass # Keep original order if partial match fails
            
        return found_months

    def sheet_exists(self, sheet_name):
        return sheet_name in self.all_sheet_names
            
    def get_monthly_data(self, sheet_name):
        """Returns raw dataframe for a month"""
        if sheet_name not in self.all_sheet_names:
            return pd.DataFrame()
            
        if self.use_gsheets:
            ws = self.xl.worksheet(sheet_name)
            return pd.DataFrame(ws.get_all_records())
        else:
            return pd.read_excel(self.file_path, sheet_name=sheet_name)

    def get_sheet_as_df(self, sheet_name):
        """Helper to get any sheet as DF"""
        if self.use_gsheets:
            ws = self.xl.worksheet(sheet_name)
            return pd.DataFrame(ws.get_all_records())
        else:
            return pd.read_excel(self.file_path, sheet_name=sheet_name)


    def get_monthly_kpis(self, month, year):
        """
        Returns (Income, Expense, Difference) for a specific month/year.
        Source: 'Budget' sheet.
        """
        try:
            budget_df = self.get_sheet_as_df("Budget")
            
            # budget_df structure expected: ['Month', ..., 'Income', 'Difference']
            # 'Month' column likely contains strings like "August 2025"
            
            target_row_str = f"{month} {year}"
            row = budget_df[budget_df['Month'] == target_row_str]
            
            if not row.empty:
                income = row.iloc[0]['Income']
                diff = row.iloc[0]['Difference']
                # Expense = Income - Difference (as per requirements)
                expense = income - diff 
                return income, expense, diff
            else:
                return 0, 0, 0
        except Exception as e:
            st.error(f"KPI Fetch Error: {e}")
            return 0, 0, 0

    def get_category_expenses(self, sheet_name):
        """
        Returns dataframe of expenses by category for the chart.
        Source: 'category total' sheet (Transposed/Pivoted) OR aggregated from Monthly Sheet?
        
        Requirement says: "Source: Category Total sheet"
        """
        try:
            # Note: Sheet name is lowercase 'category total' in file
            ct_df = self.get_sheet_as_df("category total")
            
            # Structure: Category (col) | Aug 2025 | Sep 2025 ...
            # We need to find the column that matches 'sheet_name'
            
            if sheet_name in ct_df.columns:
                # Filter where Category is NOT Income (since we want expenses)
                # And remove NaNs
                # df_filtered = ct_df[['Category', sheet_name]].dropna()
                # df_filtered = df_filtered[df_filtered['Category'] != 'Income']
                # df_filtered.columns = ['Category', 'Amount']
                # return df_filtered
                df_filtered = ct_df[['Category', sheet_name]].dropna()
                df_filtered = df_filtered[df_filtered['Category'] != 'Income']
                df_filtered.columns = ['Category', 'Amount']

                # 🔴 CRITICAL FIX: enforce numeric type
                df_filtered['Amount'] = (
                    df_filtered['Amount']
                    .astype(str)
                    .str.replace(',', '', regex=False)
                )

                df_filtered['Amount'] = pd.to_numeric(df_filtered['Amount'], errors='coerce').fillna(0)

                return df_filtered
            else:
                return pd.DataFrame()
                
        except Exception as e:
            st.error(f"Category Fetch Error: {e}")
            return pd.DataFrame()

    def get_allocation_breakdown(self, sheet_name):
        try:
            ct_df = self.get_sheet_as_df("category total")
            if sheet_name not in ct_df.columns:
                return pd.DataFrame()

            ct_df['Category'] = ct_df['Category'].astype(str).str.strip().str.lower()
            month_col = sheet_name

            def get_val(cat):
                cat = cat.lower().strip()
                row = ct_df[ct_df['Category'] == cat]
                if row.empty:
                    return 0
                val = row.iloc[0][month_col]
                if val is None or val in ["", " ", "-", "N/A"]:
                    return 0
                if isinstance(val, str):
                    val = val.replace(",", "").strip()
                try:
                    return float(val)
                except:
                    return 0

            NEED_CATS = [
                "rent", "grocery", "petrol", "gas & water", "medicine",
                "eb & ec", "emergency fund", "car maintenance", "bike maintenance",
                "relatives", "last month debt", "home app/maintenance", "emi"
            ]

            WANT_CATS = [
                "entertainment", "grooming", "trip/vacation",
                "gifts", "self improvement", "withdrawal"
            ]

            INVEST_CAT = "investment"
            OTHERS_CAT = "others"

            # Raw spend
            need_sum = sum(get_val(c) for c in NEED_CATS)
            want_sum = sum(get_val(c) for c in WANT_CATS)
            invest_sum = get_val(INVEST_CAT)

            # Split Others 50/50
            others_val = get_val(OTHERS_CAT)
            need_sum += others_val * 0.5
            want_sum += others_val * 0.5

            # Total spend
            spend_total = need_sum + want_sum

            # Income
            income = get_val("income")

            # Avoid zero edge case
            if income <= 0 and spend_total <= 0 and invest_sum <= 0:
                return pd.DataFrame()

            # Option 4 math model:
            # Investment = % of income
            invest_pct = (invest_sum / income * 100) if income > 0 else 0

            # Need/Want = % of spend (overspend friendly)
            if spend_total > 0:
                need_pct = (need_sum / spend_total * 100)
                want_pct = (want_sum / spend_total * 100)
            else:
                need_pct = want_pct = 0

            # Normalize to 100% donut
            total = need_pct + want_pct + invest_pct
            if total == 0:
                return pd.DataFrame()

            #need_pct = need_pct / total * 100
            #want_pct = want_pct / total * 100
            #invest_pct = invest_pct / total * 100

            return pd.DataFrame({
                "Type": ["Need", "Want", "Investment"],
                "Raw": [need_sum, want_sum, invest_sum],
                "Percent": [need_pct, want_pct, invest_pct]
            })

        except Exception as e:
            st.error(f"Allocation Breakdown Error: {e}")
            return pd.DataFrame()


    def get_budget_vs_actual(self, sheet_name):
        """
        Returns DataFrame for Budget (Target) vs Actual comparison by Category.
        Values are reshaped for grouped bar chart usage.
        """
        try:
            budget_df = self.get_sheet_as_df("Budget")
            
            # 1. Identify rows
            target_row = budget_df[budget_df['Month'] == 'Target']
            actual_row = budget_df[budget_df['Month'] == sheet_name]
            
            if target_row.empty or actual_row.empty:
                return pd.DataFrame()
            
            # 2. Identify Category Columns
            # Exclude known metadata columns
            exclude_cols = ['Month', 'Income', 'Difference']
            # Also exclude columns that might be completely empty or unnamed (generic safety)
            cols = [c for c in budget_df.columns if c not in exclude_cols and "Unnamed" not in str(c)]
            
            # 3. Extract Data
            data = []
            
            for col in cols:
                # Budget Value
                b_val = pd.to_numeric(target_row.iloc[0].get(col, 0), errors='coerce')
                b_val = 0 if pd.isna(b_val) else b_val
                
                # Actual Value
                a_val = pd.to_numeric(actual_row.iloc[0].get(col, 0), errors='coerce')
                a_val = 0 if pd.isna(a_val) else a_val
                
                # Only add if there's relevant data (optional: skip if both are 0?)
                # Keeping 0s might be useful to show "Budgeted 0 vs Actual 500"
                
                data.append({"Category": col, "Type": "Budget", "Amount": b_val})
                data.append({"Category": col, "Type": "Actual", "Amount": a_val})
                
            return pd.DataFrame(data)
            
        except Exception as e:
            st.error(f"Budget vs Actual Error: {e}")
            return pd.DataFrame()
