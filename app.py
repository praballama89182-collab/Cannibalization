import streamlit as st
import pandas as pd

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
    Logic to decide which Ad Group keeps the keyword and which should be negated.
    """
    max_sales_idx = group['sales_val'].idxmax()
    sales_leader = group.loc[max_sales_idx]
    
    max_roas_idx = group['calculated_roas'].idxmax()
    roas_leader = group.loc[max_roas_idx]
    
    if max_sales_idx == max_roas_idx:
        return max_sales_idx, "Best Sales & ROAS"
    
    roas_sales = sales_leader['calculated_roas']
    roas_challenger = roas_leader['calculated_roas']
    
    # Calculate if the ROAS leader is significantly better than the Volume leader
    improvement = (roas_challenger - roas_sales) / roas_sales if roas_sales > 0 else 999
    
    if (improvement >= (improvement_thresh / 100.0)) and (roas_leader['orders_val'] >= min_orders):
        return max_roas_idx, f"Efficient (ROAS +{improvement:.0%})"
    else:
        return max_sales_idx, "Volume Leader"

# --- MAIN APP ---

st.set_page_config(page_title="Cannibalization Analyzer", layout="wide")
st.title("⚔️ Search Term Cannibalization Detector")

uploaded_file = st.file_uploader("Upload Search Term Report", type=["csv", "xlsx"])

if uploaded_file:
    # 1. Load Data
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    # 2. Threshold Settings
    st.sidebar.subheader("Analysis Rules")
    roas_threshold = st.sidebar.slider("Better ROAS Threshold (%)", 30, 200, 100, 10)
    min_orders_cannibal = st.sidebar.number_input("Min Orders to Win", 1, 10, 2)

    # 3. Column Mapping (Essential to find data in PPC reports)
    col_map = {
        'term': next((c for c in df.columns if 'Matched product' in c or 'Customer Search Term' in c), None),
        'camp': next((c for c in df.columns if 'Campaign Name' in c), None),
        'adg': next((c for c in df.columns if 'Ad Group Name' in c), None),
        'match': next((c for c in df.columns if 'Match Type' in c), None),
        'orders': next((c for c in df.columns if 'Orders' in c or 'Units' in c), None),
        'sales': next((c for c in df.columns if 'Sales' in c), None),
        'spend': next((c for c in df.columns if 'Spend' in c), None),
        'clicks': next((c for c in df.columns if 'Clicks' in c), None),
    }

    if not all([col_map['term'], col_map['camp'], col_map['adg']]):
        st.error("Could not find required columns (Search Term, Campaign, Ad Group).")
    else:
        # Clean numeric data
        for c in ['orders', 'sales', 'spend', 'clicks']:
            df[col_map[c]] = pd.to_numeric(df[col_map[c]], errors='coerce').fillna(0)
        
        df['norm_match'] = df[col_map['match']].apply(normalize_match_type)

        # 4. Aggregate by Term/Campaign/AdGroup
        agg_cols = [col_map['term'], col_map['camp'], col_map['adg'], 'norm_match']
        df_agg = df.groupby(agg_cols, as_index=False).agg({
            col_map['spend']: 'sum',
            col_map['sales']: 'sum',
            col_map['orders']: 'sum',
            col_map['clicks']: 'sum'
        })

        # Rename for internal logic
        df_agg.rename(columns={
            col_map['term']: 'Search Term',
            col_map['camp']: 'Campaign',
            col_map['adg']: 'Ad Group',
            col_map['orders']: 'Orders',
            col_map['sales']: 'Sales',
            col_map['spend']: 'Spend',
            col_map['clicks']: 'Clicks'
        }, inplace=True)

        df_agg['ROAS'] = df_agg.apply(lambda x: x['Sales']/x['Spend'] if x['Spend'] > 0 else 0, axis=1)
        df_agg['CPC'] = df_agg.apply(lambda x: x['Spend']/x['Clicks'] if x['Clicks'] > 0 else 0, axis=1)

        # 5. Detect Cannibalization
        # Only look at terms that resulted in at least 1 order
        sales_df = df_agg[df_agg['Orders'] > 0].copy()
        dupe_counts = sales_df.groupby('Search Term').size()
        cannibal_list = dupe_counts[dupe_counts > 1].index.tolist()

        if cannibal_list:
            st.warning(f"Found {len(cannibal_list)} search terms appearing in multiple ad groups.")
            
            cannibal_results = []
            for term in cannibal_list:
                subset = sales_df[sales_df['Search Term'] == term].rename(
                    columns={'Sales': 'sales_val', 'Spend': 'spend_val', 'ROAS': 'calculated_roas', 'Orders': 'orders_val'}
                ).copy()
                
                # Apply the winning logic
                win_idx, reason = determine_winner(subset, roas_threshold, min_orders_cannibal) 
                
                for idx, row in subset.iterrows():
                    is_winner = (idx == win_idx)
                    cannibal_results.append({
                        'Search Term': term, 
                        'Campaign': row['Campaign'], 
                        'Ad Group': row['Ad Group'],
                        'Orders': row['orders_val'], 
                        'Sales': round(row['sales_val'], 2), 
                        'ROAS': round(row['calculated_roas'], 2), 
                        'Action': "✅ KEEP" if is_winner else "⛔ NEGATE",
                        'Winning Reason': reason if is_winner else ""
                    })

            df_final = pd.DataFrame(cannibal_results)
            
            # Display results with highlighting for negations
            st.dataframe(
                df_final.style.apply(lambda x: ['background-color: #ffebee' if 'NEGATE' in str(v) else '' for v in x], axis=1),
                use_container_width=True
            )
        else:
            st.success("No cannibalization detected! Each search term is isolated to a single ad group.")
