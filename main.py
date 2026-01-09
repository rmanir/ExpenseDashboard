import streamlit as st
import pandas as pd
from services.data_service import DataService

# Page Config
st.set_page_config(
    page_title="Expense Dashboard",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Services
@st.cache_resource
def get_data_service():
    return DataService()

data_service = get_data_service()

# --- SIDEBAR ---
with st.sidebar:
    st.title("💸 Tracker")
    
    # Year Selection
    try:
        years = data_service.get_available_years()
        if not years:
            st.error("No data found!")
            st.stop()
            
        selected_year = st.selectbox("Year", years, index=len(years)-1)
        
        # Month Selection
        months = data_service.get_months_for_year(selected_year)
        selected_month_name = st.radio("Month", months)
        
        # Construct full month string for data fetching (e.g., "August 2025")
        current_sheet_name = f"{selected_month_name} {selected_year}"
        
        st.divider()
        st.caption(f"Data Source: {'✅ Google Sheets' if data_service.use_gsheets else '📁 Local Excel'}")
        if not data_service.use_gsheets:
            st.warning("Running in Offline Mode")

    except Exception as e:
        st.error(f"Error loading metadata: {e}")
        st.stop()

# --- MAIN CONTENT ---
st.title(f"Dashboard: {selected_month_name} {selected_year}")

# Validation: Check if sheet exists
if not data_service.sheet_exists(current_sheet_name):
    st.error(f"Sheet '{current_sheet_name}' not found!")
    st.info("Available sheets: " + ", ".join(data_service.all_sheet_names))
    st.stop()

# 1. KPIs
try:
    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    
    # These functions need implementation in DataService
    income, expense, diff = data_service.get_monthly_kpis(selected_month_name, selected_year)
    
    kpi_col1.metric("Income", f"₹{income:,.0f}")
    kpi_col2.metric("Expenses", f"₹{expense:,.0f}")
    kpi_col3.metric("Savings / Diff", f"₹{diff:,.0f}", delta=f"{diff:,.0f}", delta_color="normal")
    
except Exception as e:
    st.error(f"Could not load KPIs: {e}")

st.divider()

# 2. Charts
try:
    import plotly.express as px
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("Category Spend")
        cat_df = data_service.get_category_expenses(current_sheet_name)
        if not cat_df.empty:
            # Sort for better visualization
            cat_df = cat_df.sort_values(by="Amount", ascending=True)
            fig_bar = px.bar(
                cat_df, 
                x="Amount", 
                y="Category", 
                orientation='h',
                text_auto='.2s',
                color="Amount",
                color_continuous_scale="Reds"
            )
            fig_bar.update_layout(xaxis_title="", yaxis_title="", showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No category data available.")
            
    with c2:
        st.subheader("Allocation")
        alloc_df = data_service.get_allocation_breakdown(current_sheet_name)
        if not alloc_df.empty:
            fig_pie = px.pie(
                alloc_df, 
                values="Amount", 
                names="Type", 
                hole=0.4,
                color="Type",
                color_discrete_map={
                    "Need": "#EF4444",   # Red
                    "Want": "#F59E0B",   # Amber
                    "Investment": "#10B981" # Green
                }
            )
            fig_pie.update_traces(textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No allocation data.")

    # --- New Feature: Budget vs Actual ---
    st.subheader("Budget vs Actual by Category")
    bva_df = data_service.get_budget_vs_actual(current_sheet_name)
    if not bva_df.empty:
        fig_bva = px.bar(
            bva_df,
            x="Category",
            y="Amount",
            color="Type",
            barmode='group',
            text_auto='.2s',
            color_discrete_map={
                "Budget": "#3B82F6",   # Blue
                "Actual": "#EF4444"    # Red
            }
        )
        fig_bva.update_layout(
            xaxis_title="", 
            yaxis_title="", 
            legend_title_text="",
            showlegend=True,
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig_bva, use_container_width=True)
    else:
        st.info("No Budget vs Actual data available for this month.")

except Exception as e:
    st.error(f"Chart Error: {e}")

st.divider()

# 3. Raw Data
st.subheader(f"Transactions: {current_sheet_name}")
try:
    raw_df = data_service.get_monthly_data(current_sheet_name)
    if not raw_df.empty:
        # Format Date column if it exists
        if 'Date' in raw_df.columns:
            raw_df['Date'] = pd.to_datetime(raw_df['Date']).dt.strftime('%d-%m-%Y')
            
        st.dataframe(
            raw_df, 
            use_container_width=True, 
            height=400,
            column_config={
                "Amount": st.column_config.NumberColumn(format="₹%d"),
            }
        )
    else:
        st.warning(f"No transactions found for {current_sheet_name}")
except Exception as e:
    st.error(f"Error loading table: {e}")
