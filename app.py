import streamlit as st
import pandas as pd
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Amazon Cannibalization Analyzer", page_icon="⚔️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; border: 1px solid #f0f2f6; padding: 20px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def determine_winner(group, improvement_thresh, min_orders):
    max_sales_idx = group['sales_val'].idxmax()
    sales_leader = group.loc[max_sales_idx]
    max_roas_idx = group['calculated_roas'].idxmax()
    roas_leader = group.loc[max_roas_idx]
    
    if max_sales_idx == max_roas_idx:
        return max_sales_idx, "Best Sales & ROAS"
    
    roas_sales = sales_leader['calculated_roas']
    roas_challenger = roas_leader['calculated_roas']
    improvement = (roas_challenger - roas_sales) / roas_sales if roas_sales > 0 else 999
    
    if (improvement >= (improvement_thresh / 100.0)) and (roas_leader['orders_val'] >= min_orders):
        return max_roas_idx, f"Efficient (ROAS +{improvement:.0%})"
    else:
        return max_sales_idx, "Volume Leader"

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Cannibalization_Report', index=False)
    return output.getvalue()

# --- HEADER ---
st.title("⚔️ Amazon Search Term Cannibalization Analyzer")
st.markdown("Designed by **Prabal Lama**, Senior SEO Specialist, Bangalore.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    uploaded_file = st.file_uploader("Upload Search Term Report", type=["csv", "xlsx"])
    st.divider()
    roas_threshold = st.slider("ROAS Improvement Threshold (%)", 30, 200, 100, 10)
    min_orders_cannibal = st.number_input("Min Orders for Winner", 1, 10, 2)

if uploaded_file:
    try:
        # Load Data
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        
        # Amazon Column Mapping
        col_map = {
            'term': next((c for c in df.columns if 'Search Term' in c), None),
            'camp': next((c for c in df.columns if 'Campaign Name' in c), None),
            'adg': next((c for c in df.columns if 'Ad Group Name' in c), None),
            'match': next((c for c in df.columns if 'Match Type' in c), None),
            'orders': next((c for c in df.columns if 'Orders' in c or 'Units' in c), None),
            'sales': next((c for c in df.columns if 'Sales' in c), None),
            'spend': next((c for c in df.columns if 'Spend' in c), None),
            'clicks': next((c for c in df.columns if 'Clicks' in c), None),
        }

        # Numeric Cleaning
        for c in ['orders', 'sales', 'spend', 'clicks']:
            df[col_map[c]] = pd.to_numeric(df[col_map[c]], errors='coerce').fillna(0)
        
        # --- TOTAL ACCOUNT OVERVIEW ---
        st.subheader("📊 Total Account Overview")
        acc_sales = df[col_map['sales']].sum()
        acc_spend = df[col_map['spend']].sum()
        acc_acos = (acc_spend / acc_sales * 100) if acc_sales > 0 else 0
        acc_roas = (acc_sales / acc_spend) if acc_spend > 0 else 0
        
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Total Sales", f"₹{acc_sales:,.2f}")
        o2.metric("Total Spend", f"₹{acc_spend:,.2f}")
        o3.metric("Account ACOS", f"{acc_acos:.2f}%")
        o4.metric("Account ROAS", f"{acc_roas:.2f}")

        # --- ANALYSIS LOGIC ---
        df_agg = df.groupby([col_map['term'], col_map['camp'], col_map['adg'], col_map['match']], as_index=False).agg({
            col_map['spend']: 'sum', col_map['sales']: 'sum', col_map['orders']: 'sum', col_map['clicks']: 'sum'
        })
        df_agg.rename(columns={
            col_map['term']: 'Search Term', col_map['camp']: 'Campaign', 
            col_map['adg']: 'Ad Group', col_map['orders']: 'Orders', 
            col_map['sales']: 'Sales', col_map['spend']: 'Spend', 
            col_map['clicks']: 'Clicks', col_map['match']: 'Match Type'
        }, inplace=True)
        df_agg['ROAS'] = (df_agg['Sales'] / df_agg['Spend'].replace(0, 0.01)).round(2)

        sales_df = df_agg[df_agg['Orders'] > 0].copy()
        dupe_terms = sales_df.groupby('Search Term').size()
        cannibal_list = dupe_terms[dupe_terms > 1].index.tolist()

        if cannibal_list:
            final_results = []
            for term in cannibal_list:
                subset = sales_df[sales_df['Search Term'] == term].rename(
                    columns={'Sales': 'sales_val', 'Spend': 'spend_val', 'ROAS': 'calculated_roas', 'Orders': 'orders_val'}
                ).copy()
                win_idx, reason = determine_winner(subset, roas_threshold, min_orders_cannibal)
                for idx, row in subset.iterrows():
                    is_winner = (idx == win_idx)
                    final_results.append({
                        'Search Term': term, 'Campaign': row['Campaign'], 'Ad Group': row['Ad Group'], 'Match Type': row['Match Type'],
                        'Orders': int(row['orders_val']), 'Sales': round(row['sales_val'], 2), 'Spend': round(row['spend_val'], 2),
                        'ROAS': round(row['calculated_roas'], 2), 
                        'Action': "✅ KEEP" if is_winner else "⛔ NEGATE", 'Winning Reason': reason if is_winner else ""
                    })
            df_final = pd.DataFrame(final_results)

            st.divider()
            
            # --- VISUALIZATION SECTION ---
            st.subheader("📈 Account vs. Cannibalized Sales & Spend")
            
            comp_sales = df_final['Sales'].sum()
            comp_spend = df_final['Spend'].sum()
            
            chart_data = pd.DataFrame({
                'Metric': ['Sales', 'Sales', 'Spend', 'Spend'],
                'Type': ['Total Account', 'Cannibalized Only', 'Total Account', 'Cannibalized Only'],
                'Value': [acc_sales, comp_sales, acc_spend, comp_spend]
            })
            
            # Pivot data for chart
            pivot_df = chart_data.pivot(index='Metric', columns='Type', values='Value')
            st.bar_chart(pivot_df, color=["#FF4B4B", "#232F3E"])

            # --- IMPACT SECTION ---
            st.subheader("🚩 Cannibalization Impact")
            c1, c2, c3 = st.columns(3)
            c1.metric("Competing Terms", len(cannibal_list))
            negate_spend = df_final[df_final['Action'] == '⛔ NEGATE']['Spend'].sum()
            c2.metric("Spend to Negate (Waste)", f"₹{negate_spend:,.2f}", delta=f"-{negate_spend:,.2f}", delta_color="inverse")
            sales_at_risk = df_final[df_final['Action'] == '⛔ NEGATE']['Sales'].sum()
            c3.metric("Sales Reallocated", f"₹{sales_at_risk:,.2f}")

            # --- DATA TABLE ---
            st.dataframe(df_final.style.apply(lambda x: ['background-color: #ffebee' if 'NEGATE' in str(v) else '' for v in x], axis=1), use_container_width=True)
            
            # --- EXPORT ---
            st.download_button("📥 Export Master Report", data=to_excel(df_final), file_name="Amazon_Cannibalization_Report.xlsx")
        else:
            st.success("No cannibalization detected.")

    except Exception as e:
        st.error(f"Error: {e}")
