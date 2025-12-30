import streamlit as st
import pandas as pd
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Amazon Cannibalization Analyzer",
    page_icon="⚔️",
    layout="wide"
)

# --- CREATOR INFO ---
# Created by: Prabal Lama, Senior SEO Specialist, Bangalore.

# --- HELPER FUNCTIONS ---

def normalize_match_type(val):
    if pd.isna(val): return 'UNKNOWN'
    val = str(val).upper()
    if 'EXACT' in val: return 'EXACT'
    if 'PHRASE' in val: return 'PHRASE'
    if 'BROAD' in val: return 'BROAD'
    return 'AUTO/OTHER'

def determine_winner(group, improvement_thresh, min_orders):
    """
    Logic to decide which Ad Group keeps the keyword.
    Prioritizes Sales Volume unless a challenger has significantly higher ROAS.
    """
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

# --- MAIN APP ---

st.title("⚔️ Amazon Search Term Cannibalization Analyzer")
st.markdown("""
    **Identify self-competition in your Amazon PPC.** This tool detects search terms appearing in multiple ad groups and tells you which ones to **KEEP** and which to **NEGATE**.
""")

with st.sidebar:
    st.header("⚙️ Settings")
    uploaded_file = st.file_uploader("Upload Amazon Search Term Report", type=["csv", "xlsx"])
    
    st.divider()
    st.subheader("Analysis Thresholds")
    roas_threshold = st.slider("ROAS Improvement Threshold (%)", 30, 200, 100, 10, help="If a challenger has X% better ROAS than the volume leader, it wins.")
    min_orders_cannibal = st.number_input("Min Orders for ROAS Winner", 1, 10, 2, help="Minimum orders required for an 'Efficient' winner to be valid.")

if uploaded_file:
    try:
        # Load Data
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        # Column Mapping (Amazon Standard Headers)
        col_map = {
            'term': next((c for c in df.columns if 'Customer Search Term' in c or 'Search Term' in c), None),
            'camp': next((c for c in df.columns if 'Campaign Name' in c), None),
            'adg': next((c for c in df.columns if 'Ad Group Name' in c), None),
            'match': next((c for c in df.columns if 'Match Type' in c), None),
            'orders': next((c for c in df.columns if '7 Day Total Orders' in c or 'Orders' in c or 'Units' in c), None),
            'sales': next((c for c in df.columns if '7 Day Total Sales' in c or 'Sales' in c), None),
            'spend': next((c for c in df.columns if 'Spend' in c), None),
            'clicks': next((c for c in df.columns if 'Clicks' in c), None),
        }

        if not all([col_map['term'], col_map['camp'], col_map['adg'], col_map['sales']]):
            st.error("Could not find required columns. Ensure your report includes Search Term, Campaign, Ad Group, and Sales data.")
        else:
            # Data Cleaning
            for c in ['orders', 'sales', 'spend', 'clicks']:
                df[col_map[c]] = pd.to_numeric(df[col_map[c]], errors='coerce').fillna(0)
            
            df['norm_match'] = df[col_map['match']].apply(normalize_match_type)

            # Aggregation
            agg_cols = [col_map['term'], col_map['camp'], col_map['adg'], 'norm_match']
            df_agg = df.groupby(agg_cols, as_index=False).agg({
                col_map['spend']: 'sum',
                col_map['sales']: 'sum',
                col_map['orders']: 'sum',
                col_map['clicks']: 'sum'
            })

            df_agg.rename(columns={
                col_map['term']: 'Search Term', col_map['camp']: 'Campaign',
                col_map['adg']: 'Ad Group', col_map['orders']: 'Orders',
                col_map['sales']: 'Sales', col_map['spend']: 'Spend',
                col_map['clicks']: 'Clicks'
            }, inplace=True)

            df_agg['ROAS'] = (df_agg['Sales'] / df_agg['Spend'].replace(0, 0.01)).round(2)
            df_agg['CPC'] = (df_agg['Spend'] / df_agg['Clicks'].replace(0, 1)).round(2)

            # Detection Logic
            sales_df = df_agg[df_agg['Orders'] > 0].copy()
            dupe_terms = sales_df.groupby('Search Term').size()
            cannibal_list = dupe_terms[dupe_terms > 1].index.tolist()

            if cannibal_list:
                st.subheader(f"🚩 Found {len(cannibal_list)} Cannibalized Search Terms")
                
                final_results = []
                for term in cannibal_list:
                    subset = sales_df[sales_df['Search Term'] == term].rename(
                        columns={'Sales': 'sales_val', 'Spend': 'spend_val', 'ROAS': 'calculated_roas', 'Orders': 'orders_val'}
                    ).copy()
                    
                    win_idx, reason = determine_winner(subset, roas_threshold, min_orders_cannibal)
                    
                    for idx, row in subset.iterrows():
                        is_winner = (idx == win_idx)
                        final_results.append({
                            'Search Term': term,
                            'Campaign': row['Campaign'],
                            'Ad Group': row['Ad Group'],
                            'Orders': int(row['orders_val']),
                            'Sales': round(row['sales_val'], 2),
                            'Spend': round(row['spend_val'], 2),
                            'ROAS': round(row['calculated_roas'], 2),
                            'Action': "✅ KEEP" if is_winner else "⛔ NEGATE",
                            'Winning Reason': reason if is_winner else ""
                        })

                df_final = pd.DataFrame(final_results)
                
                # Display Summary KPIs
                c1, c2 = st.columns(2)
                c1.metric("Wasted Spend (Duplicated)", f"₹{df_final[df_final['Action'] == '⛔ NEGATE']['Spend'].sum():,.2f}")
                c2.metric("Sales at Risk", f"₹{df_final[df_final['Action'] == '⛔ NEGATE']['Sales'].sum():,.2f}")

                # Display Table
                st.dataframe(
                    df_final.style.apply(lambda x: ['background-color: #ffebee' if 'NEGATE' in str(v) else '' for v in x], axis=1),
                    use_container_width=True
                )
                
                # Download
                excel_data = to_excel(df_final)
                st.download_button("📥 Download Action Plan (Excel)", data=excel_data, file_name="Amazon_Cannibalization_Report.xlsx")
            else:
                st.success("No cannibalization detected! All search terms are isolated.")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("👋 Upload your Amazon Search Term report to start detection.")
