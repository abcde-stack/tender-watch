"""
Tender Watch: Streamlit dashboard over the cleaned procurement Parquet.
Run:  cd /path/to/tender-watch
      streamlit run app/dashboard.py
Small aggregates (sum_*.parquet) load instantly; drill-downs query the big
fact/flag Parquet live via DuckDB (sub-second on columnar files).
"""
import json
from pathlib import Path
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

DATA = (Path(__file__).resolve().parent.parent / "data").as_posix()

st.set_page_config(page_title="Tender Watch", page_icon="🔎", layout="wide")


# ---------------------------------------------------------------- DB plumbing
@st.cache_resource
def con():
    return duckdb.connect()


@st.cache_data(show_spinner=False)
def q(sql: str):
    return con().execute(sql).df()


def p(name: str) -> str:
    """Quoted parquet path for use inside SQL."""
    return f"'{DATA}/{name}.parquet'"


def cr(rupees) -> str:
    """Format rupees as ₹ crore / lakh crore."""
    if rupees is None:
        return "-"
    cr_val = float(rupees) / 1e7
    if cr_val >= 1e5:
        return f"₹{cr_val/1e5:,.2f} lakh Cr"
    return f"₹{cr_val:,.2f} Cr"


# Human labels and one-line meanings for the value-quality tiers. Single source of
# truth for the Data Quality page. These describe DATA ERRORS, not wrongdoing.
VQ_LABEL = {
    "junk_magnitude": "Junk: impossibly large (over ₹10,000 Cr)",
    "junk_sequence": "Junk: placeholder digits (for example 12345678)",
    "review": "Review: very large (₹1,000 to 10,000 Cr)",
    "suspect_placeholder": "Suspect: placeholder-looking value",
}
VQ_KEEP_NOTE = {
    "junk_magnitude": "excluded from all totals",
    "junk_sequence": "excluded from all totals",
    "review": "kept in totals, may be a genuine large contract",
    "suspect_placeholder": "kept in totals, plausible value that looks like a default",
}


# our state labels -> the GeoJSON's ST_NM names (only the ones that differ).
# Note the GeoJSON merges Dadra & Nagar Haveli with Daman & Diu into one region.
STATE_TO_GEO = {
    "Andaman and Nicobar Island": "Andaman & Nicobar",
    "Chandigarh UT": "Chandigarh",
    "Dadra and Nagar Haveli (UT)": "Dadra and Nagar Haveli and Daman and Diu",
    "Daman and Diu": "Dadra and Nagar Haveli and Daman and Diu",
    "Jammu and Kashmir": "Jammu & Kashmir",
    "Ladakh UT": "Ladakh",
    "Lakshadweep UT": "Lakshadweep",
    "NCT of Delhi": "Delhi",
    "Puducherry UT": "Puducherry",
}


@st.cache_data(show_spinner=False)
def india_geo():
    """State-boundary GeoJSON for the choropleth. Returns None if the file is absent
    (a fresh checkout that did not include it) so the page degrades instead of crashing."""
    path = Path(__file__).resolve().parent / "india_states.geojson"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# Vendor-concentration (HHI) band thresholds, on the 0..10000 scale. Single source
# of truth for both the SQL CASE and the Python label, and the caption text.
HHI_HIGH, HHI_MOD = 2500, 1500


def hhi_band(x):
    """Lowercase concentration band, or None when HHI is missing (NaN/NULL)."""
    if x is None or pd.isna(x):
        return None
    return "high" if x > HHI_HIGH else "moderate" if x >= HHI_MOD else "low"


MCA_STATUS = {
    "ACTV": "Active", "STOF": "Struck Off", "UPSO": "Under process of striking off",
    "AMAL": "Amalgamated", "ULQD": "Under Liquidation", "DISD": "Dissolved",
    "CLLP": "Converted to LLP", "CLLD": "Converted to LLP & Dissolved",
    "NAEF": "Not available for e-filing", "D455": "Dormant (u/s 455)",
}
DEAD_STATUSES = {"STOF", "UPSO", "ULQD", "AMAL", "DISD", "CLLD"}


# --------------------------------------------------------------------- header
st.title("🔎 Tender Watch")
st.caption(
    "Independent analysis of India's Central Public Procurement Portal (CPPP). "
    "Flags are **statistical indicators**, not accusations of wrongdoing."
)

page = st.sidebar.radio(
    "View",
    ["Overview", "Red-flag explorer", "States", "Central", "Vendors", "Departments",
     "Search", "Data Quality", "Methodology"],
)
st.sidebar.markdown("---")
st.sidebar.info(
    "Look up a record on the source portal using its **Tender ID** "
    "(for example `2021_NTPC_123456_1`):\n\n"
    "• **Award of Contract (AOC)**: "
    "[Result of Tenders](https://eprocure.gov.in/cppp/resultoftendersnew/mmpdata)\n\n"
    "• **Tenders**: "
    "[Tender Search](https://eprocure.gov.in/cppp/tendersearch/cpppdata/)\n\n"
    "**Note:** many public sector awards (for example NTPC) carry only an internal "
    "**reference number** like `4000xxxxxx`, not a standard Tender ID. The central "
    "portal has no reference-number search, so these cannot be found there. Verify "
    "them on the data source below, or by searching the title and organisation."
)
st.sidebar.caption(
    "**Data:** CPPP procurement via "
    "[tender.sarthaksidhant.com](https://tender.sarthaksidhant.com/) "
    "(eprocure.gov.in mirror); MCA company data via "
    "[data.gov.in](https://www.data.gov.in/) under GODL-India. Snapshot 26 June 2026."
)
st.sidebar.caption(
    "Flags are statistical indicators, not accusations. See the **Methodology** page "
    "for the full disclaimer and corrections policy."
)


# ------------------------------------------------------------------- Overview
if page == "Overview":
    o = q(f"SELECT * FROM {p('sum_overview')}").iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Awards", f"{int(o.total_awards):,}")
    c2.metric("Tender notices", f"{int(o.total_tenders):,}")
    c3.metric("Awarded value", cr(o.total_value))
    c4.metric(
        "Single-bid awards",
        f"{int(o.n_single_bid):,}",
        f"{100*o.n_single_bid/o.total_awards:.1f}% of awards",
    )
    c1, c2 = st.columns(2)
    c1.metric("Distinct vendors", f"{int(o.total_vendors):,}")
    c2.metric("Organisations", f"{int(o.total_orgs):,}")

    st.subheader("Awards & single-bid share by year")
    yr = q(
        f"SELECT award_year, n_awards, n_single_bid, "
        f"round(100.0*n_single_bid/n_awards,1) AS single_bid_pct, "
        f"round(total_value/1e7,2) AS value_cr "
        f"FROM {p('sum_year')} WHERE award_year BETWEEN 2010 AND 2026 ORDER BY award_year"
    )
    yr["year"] = yr["award_year"].astype(int).astype(str)  # categorical axis: no comma/decimal
    a, b = st.columns(2)
    a.bar_chart(yr, x="year", y="n_awards", height=300)
    b.line_chart(yr, x="year", y="single_bid_pct", height=300)
    st.caption("Awarded value by year (₹ Cr, disclosed values only)")
    st.bar_chart(yr, x="year", y="value_cr", height=260)

    st.subheader("Red-flag totals (across all awards)")
    fl = q(f"SELECT flag, n FROM {p('sum_flag')} ORDER BY n DESC")
    st.bar_chart(fl, x="flag", y="n", height=300)

    st.subheader("Risk-score distribution")
    rk = q(f"SELECT risk_score, n_awards FROM {p('sum_risk')} ORDER BY risk_score")
    st.bar_chart(rk, x="risk_score", y="n_awards", height=260)
    st.caption(
        "How many awards sit at each weighted risk score (0 = no flags, up to 9). "
        "Most awards score low; the high-scoring tail is where to look first."
    )

    st.subheader("Awards by calendar month (fiscal year-end clustering)")
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    yrs = q(
        f"SELECT DISTINCT award_year FROM {p('sum_month')} "
        f"WHERE award_year BETWEEN 2010 AND 2026 ORDER BY award_year DESC"
    )["award_year"].tolist()
    yr_pick = st.selectbox("Year", ["All years"] + [int(y) for y in yrs], index=0, key="fy_year")
    where = "" if yr_pick == "All years" else f"WHERE award_year = {int(yr_pick)}"
    mo = q(
        f"SELECT award_month, sum(n_awards) AS n_awards FROM {p('sum_month')} "
        f"{where} GROUP BY award_month ORDER BY award_month"
    )
    mo["month"] = mo["award_month"].map(lambda m: MONTHS[int(m) - 1])
    mo["period"] = mo["award_month"].map(
        lambda m: "Jan to Mar (year-end)" if m in (1, 2, 3) else "Apr to Dec"
    )
    by_m = dict(zip(mo.award_month.astype(int), mo.n_awards))
    tot_m = sum(by_m.values()) or 1
    mar_pct = 100 * by_m.get(3, 0) / tot_m
    q4_pct = 100 * (by_m.get(1, 0) + by_m.get(2, 0) + by_m.get(3, 0)) / tot_m
    e1, e2 = st.columns(2)
    e1.metric("Share of awards in March", f"{mar_pct:.1f}%",
              f"{mar_pct - 100/12:+.1f} pts vs an even month")
    e2.metric("Share in Jan to Mar (year-end)", f"{q4_pct:.1f}%",
              f"{q4_pct - 25:+.1f} pts vs an even quarter")
    figm = px.bar(
        mo, x="month", y="n_awards", color="period",
        category_orders={"month": MONTHS},
        color_discrete_map={"Jan to Mar (year-end)": "#c0392b", "Apr to Dec": "#95a5a6"},
        labels={"n_awards": "Awards", "month": "Month"},
    )
    figm.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=320, legend_title="")
    st.plotly_chart(figm, use_container_width=True)
    st.caption(
        "India's financial year ends 31 March. A rise in awards toward year-end "
        "(Jan to Mar) and the dip just after (April) is a recognised budget-flush "
        "pattern. Awards with no recorded date are excluded. Figures are "
        "pre-deduplication."
    )

    matched = int(q(
        f"SELECT count(*) AS m FROM {p('fact_award')} WHERE tender_id IN "
        f"(SELECT tender_id FROM {p('fact_tender')} WHERE tender_id IS NOT NULL AND tender_id <> '')"
    ).iloc[0].m)
    pct = 100 * matched / int(o.total_awards)
    st.info(
        f"**Coverage caveat, read before interpreting flags.** Only "
        f"**{matched:,} awards ({pct:.0f}%)** could be linked to a tender notice. "
        "The **Short window / Low EMD / High fee / Corrigendum** flags (and the upper "
        "risk-score range) apply only to that matched subset, so their totals "
        "**under-state reality**. **Single bid / Zero bids** are "
        f"reliable across all {int(o.total_awards):,} awards. Implausible or "
        "placeholder contract values are listed on the **Data Quality** page."
    )


# ----------------------------------------------------------- Red-flag explorer
elif page == "Red-flag explorer":
    st.subheader("Filter awards by red flag")
    f1, f2, f3 = st.columns(3)
    yr_min, yr_max = f1.select_slider(
        "Award year", options=list(range(2010, 2027)), value=(2020, 2026)
    )
    flags = f2.multiselect(
        "Must have flag(s)",
        ["Single bid", "Zero bids", "Short window",
         "Low EMD", "High fee", "Corrigendum"],
        default=["Single bid"],
    )
    min_risk = f3.slider("Min risk score", 0, 9, 0)
    org_kw = st.text_input("Organisation contains", "")

    if {"Short window", "Low EMD", "High fee", "Corrigendum"} & set(flags):
        st.warning(
            "⚠️ A notice-linked flag is selected. These only cover the ~24% of "
            "awards matched to a tender notice, so this is a partial (lower-bound) view."
        )

    flagcol = {
        "Single bid": "f.f_single_bid", "Zero bids": "f.f_zero_bid",
        "Short window": "f.f_short_window",
        "Low EMD": "f.f_low_emd", "High fee": "f.f_high_fee",
        "Corrigendum": "f.f_corrigendum",
    }
    where = [f"a.award_year BETWEEN {yr_min} AND {yr_max}",
             f"f.risk_score >= {min_risk}"]
    where += [f"{flagcol[x]}" for x in flags]
    if org_kw.strip():
        kw = org_kw.replace("'", "''")
        where.append(f"o.org_name ILIKE '%{kw}%'")
    sql = f"""
        SELECT a.award_year AS year, a.title, o.org_name AS organisation,
               a.winner_name_raw AS winner,
               round(a.contract_value_inr / 1e7, 3) AS value_cr,
               a.bids_received AS bids, f.risk_score, a.portal_id
        FROM {p('fact_award')} a
        LEFT JOIN {p('flag_award')} f USING (internal_id)
        LEFT JOIN {p('sum_org')} o ON o.org_id = a.org_id
        WHERE {' AND '.join(where)}
        ORDER BY f.risk_score DESC, a.contract_value_inr DESC NULLS LAST
        LIMIT 500
    """
    df = q(sql)
    st.caption("Showing up to 500 of the matching awards.")
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.3f"),
            "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
        },
    )
    st.download_button(
        "⬇ Download these results (CSV)", df.to_csv(index=False).encode(),
        "red_flag_awards.csv", "text/csv",
    )


# -------------------------------------------------------------------- Vendors
elif page == "Vendors":
    st.subheader("Vendor leaderboard")
    c1, c2 = st.columns(2)
    min_awards = c1.slider("Min awards won", 1, 500, 50)
    sort_by = c2.selectbox(
        "Rank by", ["single_bid_pct", "n_awards", "total_value"], index=0
    )
    df = q(
        f"SELECT vendor_name, n_awards, n_single_bid, single_bid_pct, "
        f"round(total_value / 1e7, 2) AS total_value_cr, n_orgs FROM {p('sum_vendor')} "
        f"WHERE n_awards >= {min_awards} ORDER BY {sort_by} DESC LIMIT 300"
    )
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
            "total_value_cr": st.column_config.NumberColumn("Total value (₹ Cr)", format="%.2f"),
        },
    )
    st.caption(
        "High award count **combined with** ~100% single-bid and a single "
        "organisation is the strongest pattern worth a closer look."
    )
    st.download_button(
        "⬇ Download leaderboard (CSV)", df.to_csv(index=False).encode(),
        "vendor_leaderboard.csv", "text/csv",
    )

    # ---- drill-down ----
    st.markdown("---")
    st.subheader("Vendor drill-down")
    name_kw = st.text_input("Search a vendor by name", "")
    if name_kw.strip():
        kw = name_kw.replace("'", "''")
        matches = q(
            f"SELECT vendor_id, name_raw, address_raw, address_hash "
            f"FROM {p('dim_vendor')} WHERE name_raw ILIKE '%{kw}%' "
            f"ORDER BY length(name_raw) LIMIT 50"
        )
        if not len(matches):
            st.caption("No vendors match that search.")
        else:
            pick = st.selectbox("Select vendor", matches.name_raw.tolist())
            row = matches[matches.name_raw == pick].iloc[0]
            vid = row.vendor_id

            s = q(f"SELECT n_awards, total_value, single_bid_pct, n_orgs "
                  f"FROM {p('sum_vendor')} WHERE vendor_id = '{vid}'")
            if len(s):
                s = s.iloc[0]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Awards won", f"{int(s.n_awards):,}")
                m2.metric("Total value", cr(s.total_value))
                m3.metric("Single-bid %", f"{s.single_bid_pct:.1f}%")
                m4.metric("Departments", f"{int(s.n_orgs):,}")

            if pd.notna(row.address_raw) and str(row.address_raw).strip():
                st.caption(f"📍 {row.address_raw}")

            # ---- MCA corporate identity (unambiguous exact matches only) ----
            mca = q(
                f"SELECT cin, company_name, status, reg_date, reg_state, "
                f"paidup_capital, mca_namesakes FROM {p('vendor_cin')} "
                f"WHERE vendor_id = '{vid}'"
            )
            if len(mca) and int(mca.iloc[0].mca_namesakes) == 1:
                r = mca.iloc[0]
                st.markdown("**Corporate identity**: _likely MCA match, verify on portal_")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("CIN", str(r.cin))
                k2.metric("Status", MCA_STATUS.get(str(r.status), str(r.status)))
                k3.metric("Incorporated", str(r.reg_date)[:10] if pd.notna(r.reg_date) else "-")
                k4.metric("Paid-up capital",
                          cr(r.paidup_capital) if pd.notna(r.paidup_capital) and r.paidup_capital else "-")
                reg_state = r.reg_state if pd.notna(r.reg_state) else "state not recorded"
                st.caption(f"Registered: {r.company_name} · {reg_state}")

                # time-proof flag: won at/before incorporation, or very young
                if pd.notna(r.reg_date):
                    chk = q(
                        f"SELECT count(*) FILTER (WHERE contract_at < DATE '{str(r.reg_date)[:10]}') AS before_incorp, "
                        f"count(*) FILTER (WHERE contract_at >= DATE '{str(r.reg_date)[:10]}' "
                        f"AND contract_at < DATE '{str(r.reg_date)[:10]}' + INTERVAL 365 DAY) AS within_1yr "
                        f"FROM {p('fact_award')} WHERE vendor_id = '{vid}' AND contract_at IS NOT NULL"
                    ).iloc[0]
                    if int(chk.before_incorp) > 0:
                        st.info(
                            f"ℹ️ The matched company was incorporated **after** "
                            f"{int(chk.before_incorp)} of this bidder's awards. This usually means "
                            "the bidder was an **earlier proprietorship/firm of the same name**, or "
                            "the name match is imprecise, **not necessarily irregular**. Verify on MCA."
                        )
                    elif int(chk.within_1yr) > 0:
                        st.info(
                            f"ℹ️ {int(chk.within_1yr)} of this bidder's awards fall within 1 year of "
                            "the matched company's incorporation. **Context only**: could be a newly "
                            "incorporated successor firm. Verify on MCA."
                        )
                if str(r.status) in DEAD_STATUSES:
                    st.caption(
                        f"ℹ️ Current MCA status is *{MCA_STATUS.get(str(r.status), r.status)}*. "
                        "This is a **present-day snapshot** (no strike-off date), so it does not by "
                        "itself mean the company was inactive when it won: context, not proof."
                    )
            elif len(mca):
                st.caption(
                    "ℹ️ MCA name match is ambiguous (multiple companies share this name): "
                    "identity hidden to avoid misattribution."
                )

            vts = q(
                f"SELECT award_year AS year, count(*) AS awards FROM {p('fact_award')} "
                f"WHERE vendor_id = '{vid}' AND award_year BETWEEN 2010 AND 2026 "
                f"GROUP BY award_year ORDER BY award_year"
            )
            if len(vts) > 1:
                vts["year"] = vts["year"].astype(int).astype(str)  # categorical: no comma/decimal
                st.markdown("**Awards over time**")
                st.line_chart(vts, x="year", y="awards", height=220)

            st.markdown("**Departments this vendor wins from**")
            dep = q(
                f"SELECT o.org_name_raw AS organisation, count(*) AS awards, "
                f"round(sum(a.contract_value_inr)/1e7, 2) AS value_cr "
                f"FROM {p('fact_award')} a LEFT JOIN {p('dim_org')} o ON o.org_id = a.org_id "
                f"WHERE a.vendor_id = '{vid}' GROUP BY o.org_name_raw ORDER BY awards DESC LIMIT 50"
            )
            st.dataframe(dep, width="stretch", hide_index=True)

            st.markdown("**Awards won** (top 500 by value)")
            aw = q(
                f"SELECT a.award_year AS year, a.title, o.org_name_raw AS organisation, "
                f"round(a.contract_value_inr/1e7, 3) AS value_cr, a.bids_received AS bids, "
                f"a.portal_id FROM {p('fact_award')} a "
                f"LEFT JOIN {p('dim_org')} o ON o.org_id = a.org_id "
                f"WHERE a.vendor_id = '{vid}' "
                f"ORDER BY a.contract_value_inr DESC NULLS LAST LIMIT 500"
            )
            st.dataframe(
                aw, width="stretch", hide_index=True,
                column_config={
                    "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.3f"),
                    "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
                },
            )
            st.download_button(
                "⬇ Download this vendor's awards (CSV)", aw.to_csv(index=False).encode(),
                f"vendor_awards.csv", "text/csv",
            )

            # shared-address cluster (skip the empty-address hash)
            EMPTY = "d41d8cd98f00b204e9800998ecf8427e"  # md5('')
            if row.address_hash and row.address_hash != EMPTY:
                shared = q(
                    f"SELECT name_raw AS other_vendor FROM {p('dim_vendor')} "
                    f"WHERE address_hash = '{row.address_hash}' AND vendor_id <> '{vid}' LIMIT 50"
                )
                if len(shared):
                    st.markdown(
                        f"**⚠️ {len(shared)} other vendor(s) registered at the same address** "
                        "(worth checking for related/shell entities)."
                    )
                    st.dataframe(shared, width="stretch", hide_index=True)


# ---------------------------------------------------------------- Departments
elif page == "Departments":
    st.subheader("Department / organisation scorecard")
    c1, c2, c3 = st.columns(3)
    min_awards = c1.slider("Min awards", 1, 2000, 200)
    level = c2.multiselect(
        "Govt level", ["central", "state", "psu", "bank", "other"],
        default=["central", "state", "psu", "bank", "other"],
    )
    sort = c3.selectbox(
        "Rank by",
        ["single_bid_pct", "hhi_count", "hhi_value", "n_awards", "total_value"], index=0
    )
    lv = ",".join(f"'{x}'" for x in level) or "''"
    df = q(
        f"SELECT org_name, govt_level, n_awards, single_bid_pct, hhi_count, hhi_value, "
        f"CASE WHEN hhi_count IS NULL THEN NULL WHEN hhi_count > {HHI_HIGH} THEN 'High' "
        f"WHEN hhi_count >= {HHI_MOD} THEN 'Moderate' ELSE 'Low' END AS concentration, "
        f"value_disclosed_pct, round(total_value / 1e7, 2) AS total_value_cr, n_vendors "
        f"FROM {p('sum_org')} "
        f"WHERE n_awards >= {min_awards} AND govt_level IN ({lv}) "
        f"ORDER BY {sort} DESC NULLS LAST LIMIT 300"
    )
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
            "hhi_count": st.column_config.NumberColumn("HHI (count)", format="%.0f"),
            "hhi_value": st.column_config.NumberColumn("HHI (value)", format="%.0f"),
            "value_disclosed_pct": st.column_config.NumberColumn("Value disclosed %", format="%.1f"),
            "total_value_cr": st.column_config.NumberColumn("Total value (₹ Cr)", format="%.2f"),
        },
    )
    st.caption(
        "Higher single-bid % with few distinct vendors = lower competition. **HHI** measures "
        "how concentrated an organisation's awards are among its vendors, on a 0 to 10000 "
        f"scale (above {HHI_HIGH} highly concentrated, {HHI_MOD} to {HHI_HIGH} moderate, "
        f"below {HHI_MOD} unconcentrated). **HHI (count)** uses the number of awards; "
        "**HHI (value)** uses "
        "rupees and covers only the awards with a disclosed value (see **Value disclosed %**), "
        "so it is blank or thin for bodies that do not publish values. Raise **Min awards** "
        "before trusting either, since a body with very few awards scores high automatically. "
        "Both are a lower bound, because unmerged vendor name variants split shares."
    )
    st.download_button(
        "⬇ Download scorecard (CSV)", df.to_csv(index=False).encode(),
        "org_scorecard.csv", "text/csv",
    )

    # ---- concentration vs competition scatter ----
    st.markdown("**Concentration vs competition** (each dot is an organisation)")
    scat = q(
        f"SELECT org_name, govt_level, n_awards, single_bid_pct, hhi_count, "
        f"round(coalesce(total_value,0)/1e7,2) AS value_cr FROM {p('sum_org')} "
        f"WHERE n_awards >= {min_awards} AND govt_level IN ({lv}) AND hhi_count IS NOT NULL "
        f"ORDER BY n_awards DESC LIMIT 500"
    )
    figsc = px.scatter(
        scat, x="hhi_count", y="single_bid_pct", size="value_cr", color="govt_level",
        hover_name="org_name", size_max=40,
        labels={"hhi_count": "HHI (count, concentration)", "single_bid_pct": "Single-bid %",
                "govt_level": "Govt level"},
    )
    figsc.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=480)
    st.plotly_chart(figsc, use_container_width=True)
    st.caption(
        "Top-right means concentrated (few vendors) and uncompetitive (mostly single-bid), "
        "the corner worth a closer look. Dot size is total disclosed value. "
        "HHI is unreliable at low award counts, so raise Min awards. Pre-deduplication."
    )

    # ---- organisation drill-down ----
    st.markdown("---")
    st.subheader("Organisation drill-down")
    okw = st.text_input("Search an organisation by name", "")
    if okw.strip():
        kw = okw.replace("'", "''")
        om = q(
            f"SELECT org_id, org_name_raw, govt_level FROM {p('dim_org')} "
            f"WHERE org_name_raw ILIKE '%{kw}%' ORDER BY length(org_name_raw) LIMIT 50"
        )
        if not len(om):
            st.caption("No organisations match that search.")
        else:
            opick = st.selectbox("Select organisation", om.org_name_raw.tolist())
            orow = om[om.org_name_raw == opick].iloc[0]
            oid = orow.org_id

            s = q(f"SELECT n_awards, total_value, single_bid_pct, n_vendors, "
                  f"hhi_count, hhi_value, value_disclosed_pct "
                  f"FROM {p('sum_org')} WHERE org_id = '{oid}'")
            if len(s):
                s = s.iloc[0]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Awards", f"{int(s.n_awards):,}")
                m2.metric("Total value", cr(s.total_value))
                m3.metric("Single-bid %", f"{s.single_bid_pct:.1f}%")
                m4.metric("Distinct vendors", f"{int(s.n_vendors):,}")

                if pd.notna(s.hhi_count):
                    hhi = float(s.hhi_count)
                    conc = f"by count {hhi:,.0f} ({hhi_band(hhi)})"
                    if pd.notna(s.hhi_value):
                        hv = float(s.hhi_value)
                        conc += (
                            f", by value {hv:,.0f} ({hhi_band(hv)}) over the "
                            f"{s.value_disclosed_pct:.0f}% of awards with a disclosed value"
                        )
                    st.caption(
                        f"Govt level: {orow.govt_level} · vendor concentration HHI: {conc}. "
                        "HHI is a lower bound and is unreliable when awards are few."
                    )
                else:
                    st.caption(
                        f"Govt level: {orow.govt_level} · vendor concentration HHI not "
                        "available (no awards with an identified vendor)."
                    )
            else:
                st.caption(f"Govt level: {orow.govt_level}")

            ots = q(
                f"SELECT award_year AS year, count(*) AS awards FROM {p('fact_award')} "
                f"WHERE org_id = '{oid}' AND award_year BETWEEN 2010 AND 2026 "
                f"GROUP BY award_year ORDER BY award_year"
            )
            if len(ots) > 1:
                ots["year"] = ots["year"].astype(int).astype(str)  # categorical: no comma/decimal
                st.markdown("**Awards over time**")
                st.line_chart(ots, x="year", y="awards", height=220)

            st.markdown("**Red-flag counts for this organisation**")
            fb = q(
                f"SELECT count(*) FILTER (WHERE f_single_bid)   AS single_bid, "
                f"count(*) FILTER (WHERE f_zero_bid)            AS zero_bid, "
                f"count(*) FILTER (WHERE f_short_window)        AS short_window, "
                f"count(*) FILTER (WHERE f_corrigendum)         AS corrigendum "
                f"FROM {p('flag_award')} WHERE org_id = '{oid}'"
            )
            st.dataframe(fb, width="stretch", hide_index=True)

            st.markdown("**Top vendors winning from this organisation** (concentration)")
            tv = q(
                f"SELECT v.name_raw AS vendor, count(*) AS awards, "
                f"round(100.0*count(*) / (SELECT count(*) FROM {p('fact_award')} "
                f"WHERE org_id = '{oid}' AND vendor_id IS NOT NULL), 1) AS share_pct, "
                f"round(sum(a.contract_value_inr)/1e7, 2) AS value_cr, "
                f"round(100.0*count(*) FILTER (WHERE fl.f_single_bid)/count(*), 1) AS single_bid_pct "
                f"FROM {p('fact_award')} a JOIN {p('dim_vendor')} v ON v.vendor_id = a.vendor_id "
                f"LEFT JOIN {p('flag_award')} fl USING (internal_id) "
                f"WHERE a.org_id = '{oid}' GROUP BY v.name_raw ORDER BY awards DESC LIMIT 50"
            )
            st.dataframe(
                tv, width="stretch", hide_index=True,
                column_config={
                    "share_pct": st.column_config.NumberColumn("Share of awards %", format="%.1f"),
                    "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.2f"),
                    "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
                },
            )

            st.markdown("**Flagged awards** (risk score ≥ 1, top 300 by value)")
            fa = q(
                f"SELECT a.title, round(a.contract_value_inr/1e7, 3) AS value_cr, "
                f"a.bids_received AS bids, fl.risk_score, "
                f"(a.contract_value_inr > 0 AND a.contract_value_inr % 100000 = 0) AS round_number, "
                f"a.contract_at AS award_date, a.portal_type AS portal, a.portal_id "
                f"FROM {p('fact_award')} a LEFT JOIN {p('flag_award')} fl USING (internal_id) "
                f"WHERE a.org_id = '{oid}' AND fl.risk_score >= 1 "
                f"ORDER BY fl.risk_score DESC, a.contract_value_inr DESC NULLS LAST LIMIT 300"
            )
            st.dataframe(
                fa, width="stretch", hide_index=True,
                column_config={
                    "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.3f"),
                    "round_number": st.column_config.CheckboxColumn("Round ₹1L"),
                    "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
                },
            )
            st.download_button(
                "⬇ Download flagged awards (CSV)", fa.to_csv(index=False).encode(),
                "org_flagged_awards.csv", "text/csv",
            )


# -------------------------------------------------------------------- Search
elif page == "Search":
    st.subheader("Search tenders & awards")
    kw = st.text_input("Keywords (space-separated, all must match)", "")
    src = st.radio("Dataset", ["Awards", "Tender notices"], horizontal=True)

    if kw.strip():
        terms = [t.replace("'", "''") for t in kw.split() if t.strip()]
        if src == "Awards":
            conds = " AND ".join(
                f"(a.title ILIKE '%{t}%' OR a.description ILIKE '%{t}%')" for t in terms
            )
            sql = f"""
                SELECT a.award_year AS year, a.title, o.org_name_raw AS organisation,
                       a.winner_name_raw AS winner,
                       round(a.contract_value_inr/1e7, 3) AS value_cr, a.portal_id
                FROM {p('fact_award')} a
                LEFT JOIN {p('dim_org')} o ON o.org_id = a.org_id
                WHERE {conds}
                ORDER BY a.contract_value_inr DESC NULLS LAST LIMIT 300
            """
        else:
            conds = " AND ".join(
                f"(t.title ILIKE '%{x}%' OR t.work_description ILIKE '%{x}%')" for x in terms
            )
            sql = f"""
                SELECT t.epublished_at AS published, t.title, o.org_name_raw AS organisation,
                       t.tender_category AS category, t.emd_inr AS emd, t.tender_id AS portal_id
                FROM {p('fact_tender')} t
                LEFT JOIN {p('dim_org')} o ON o.org_id = t.org_id
                WHERE {conds}
                ORDER BY t.epublished_at DESC NULLS LAST LIMIT 300
            """
        df = q(sql)
        st.caption(f"Showing up to 300 matches.")
        st.dataframe(
            df, width="stretch", hide_index=True,
            column_config={
                "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.3f"),
                "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
            },
        )
        st.download_button(
            "⬇ Download results (CSV)", df.to_csv(index=False).encode(),
            "search_results.csv", "text/csv",
        )
    else:
        st.caption("Enter one or more keywords to search titles and descriptions.")


# -------------------------------------------------------------------- States
elif page == "States":
    st.subheader("State procurement (state portals)")
    st.caption(
        "Covers ~1.93M awards from state e-procurement portals. "
        "Central / PSU / defence awards are not state-attributable and are excluded here."
    )

    sort = st.selectbox(
        "Rank states by", ["single_bid_pct", "awards", "total_value", "n_vendors"], index=0
    )
    ss = q(
        f"SELECT state, awards, value_disclosed_pct, total_value, "
        f"round(total_value/1e7, 2) AS total_value_cr, single_bid_pct, "
        f"n_units, n_vendors FROM {p('sum_state')} ORDER BY {sort} DESC"
    )
    st.dataframe(
        ss.drop(columns=["total_value"]), width="stretch", hide_index=True,
        column_config={
            "total_value_cr": st.column_config.NumberColumn("Total value (₹ Cr)", format="%.2f"),
            "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
            "value_disclosed_pct": st.column_config.NumberColumn("Value disclosed %", format="%.1f"),
        },
    )
    st.download_button(
        "⬇ Download state summary (CSV)", ss.to_csv(index=False).encode(),
        "state_summary.csv", "text/csv",
    )

    # ---- top states bar ----
    metric_col = "total_value_cr" if sort == "total_value" else sort
    metric_lbl = {
        "single_bid_pct": "Single-bid %", "awards": "Awards",
        "total_value_cr": "Total value (₹ Cr)", "n_vendors": "Distinct vendors",
    }[metric_col]
    st.markdown(f"**Top states by {metric_lbl}**")
    topn = ss.nlargest(15, metric_col)[["state", metric_col]].sort_values(metric_col)
    figts = px.bar(
        topn, x=metric_col, y="state", orientation="h",
        labels={metric_col: metric_lbl, "state": ""},
        color_discrete_sequence=["#c0392b"],
    )
    figts.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=420)
    st.plotly_chart(figts, use_container_width=True)

    # ---- choropleth map ----
    st.markdown("**Map**")
    geo = india_geo()
    if geo is None:
        st.info("Map unavailable: app/india_states.geojson is missing from this checkout.")
    else:
        # n_vendors is deliberately not a map metric: it is a distinct count and cannot
        # be summed across the states that merge into one geojson region (Dadra & Nagar
        # Haveli + Daman & Diu), which would double-count shared vendors.
        map_metric = st.selectbox(
            "Colour states by",
            ["single_bid_pct", "awards", "total_value_cr", "value_disclosed_pct"],
            index=0,
            format_func=lambda c: {
                "single_bid_pct": "Single-bid %", "awards": "Awards",
                "total_value_cr": "Total value (₹ Cr)",
                "value_disclosed_pct": "Value disclosed %",
            }[c],
            key="states_map_metric",
        )
        geo_names = {f["properties"]["ST_NM"] for f in geo["features"]}
        md = ss.copy()
        md["geo"] = md["state"].map(lambda s: STATE_TO_GEO.get(s, s))
        unmapped = sorted(set(md["geo"]) - geo_names)
        if unmapped:
            st.warning(
                "These states could not be placed on the map (name not found in the "
                f"boundary file): {', '.join(unmapped)}."
            )
        # carry numerators so percentages re-aggregate correctly where geo regions merge
        md["_sb"] = md["awards"] * md["single_bid_pct"] / 100.0
        md["_vd"] = md["awards"] * md["value_disclosed_pct"] / 100.0
        g = md.groupby("geo", as_index=False).agg(
            awards=("awards", "sum"),
            total_value_cr=("total_value_cr", "sum"),
            _sb=("_sb", "sum"),
            _vd=("_vd", "sum"),
        )
        g["single_bid_pct"] = (100.0 * g["_sb"] / g["awards"]).round(1)
        g["value_disclosed_pct"] = (100.0 * g["_vd"] / g["awards"]).round(1)
        # include every geojson state so the full map renders (blank = no state-portal data)
        all_states = pd.DataFrame({"geo": list(geo_names)})
        g = all_states.merge(g, on="geo", how="left")
        fig = px.choropleth(
            g, geojson=geo, locations="geo", featureidkey="properties.ST_NM",
            color=map_metric, color_continuous_scale="Reds",
            hover_data=["awards", "single_bid_pct", "total_value_cr", "value_disclosed_pct"],
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=600)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "State e-procurement portals only. States shown blank have no state-portal "
            "awards in this dataset (for example Gujarat, Karnataka, Bihar, Chhattisgarh, "
            "which run their own systems). Hover for details."
        )

    st.markdown("---")
    st.subheader("State → procuring units (departments)")
    state_pick = st.selectbox("Select state", ss.state.tolist())
    s = ss[ss.state == state_pick].iloc[0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Awards", f"{int(s.awards):,}")
    m2.metric("Total value", cr(s.total_value))
    m3.metric("Single-bid %", f"{s.single_bid_pct:.1f}%")
    m4.metric("Procuring units", f"{int(s.n_units):,}")
    st.caption(
        f"Value disclosed on {s.value_disclosed_pct:.1f}% of awards · "
        f"{int(s.n_vendors):,} distinct vendors"
    )

    sp = state_pick.replace("'", "''")
    st.markdown("**Procuring units in this state** (each is a buying office; top 500 by awards)")
    ukw = st.text_input("Filter units by name", "")
    where = f"state = '{sp}'"
    if ukw.strip():
        where += f" AND unit ILIKE '%{ukw.replace(chr(39), chr(39)*2)}%'"
    units = q(
        f"SELECT unit, awards, round(total_value/1e7, 2) AS value_cr, "
        f"single_bid_pct, n_vendors FROM {p('sum_state_unit')} "
        f"WHERE {where} ORDER BY awards DESC LIMIT 500"
    )
    st.dataframe(
        units, width="stretch", hide_index=True,
        column_config={
            "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.2f"),
            "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
        },
    )
    st.download_button(
        "⬇ Download units (CSV)", units.to_csv(index=False).encode(),
        "state_units.csv", "text/csv",
    )

    ALL_STATE = "All awards in this state"
    pick_u = st.selectbox(
        "Show awards for", [ALL_STATE] + (units.unit.tolist() if len(units) else [])
    )
    base = (
        f"SELECT a.award_year AS year, a.title, a.winner_name_raw AS winner, "
        f"round(a.contract_value_inr/1e7, 3) AS value_cr, a.bids_received AS bids, "
        f"fl.risk_score, a.portal_id "
        f"FROM {p('state_award')} sa JOIN {p('fact_award')} a USING (internal_id) "
        f"LEFT JOIN {p('flag_award')} fl USING (internal_id) WHERE sa.state = '{sp}' "
    )
    if pick_u == ALL_STATE:
        aw = q(base + "ORDER BY a.contract_value_inr DESC NULLS LAST LIMIT 300")
    else:
        aw = q(base + f"AND sa.unit = '{pick_u.replace(chr(39), chr(39)*2)}' "
                      "ORDER BY a.contract_value_inr DESC NULLS LAST LIMIT 300")
    st.dataframe(
        aw, width="stretch", hide_index=True,
        column_config={
            "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.3f"),
            "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
        },
    )
    st.download_button(
        "⬇ Download these awards (CSV)", aw.to_csv(index=False).encode(),
        "state_awards.csv", "text/csv",
    )


# ------------------------------------------------------------------- Central
elif page == "Central":
    st.subheader("Central government procurement")
    st.caption(
        "Covers ~1.44M awards from central ministries, PSUs, banks and autonomous "
        "bodies. ⚠️ Many PSUs (e.g. BHEL) publish **no contract value**: check the "
        "*Value disclosed %* column before trusting value figures. Ranking defaults "
        "to single-bid %, which is reliable for everyone."
    )

    types = q(
        f"SELECT DISTINCT coalesce(org_type,'Unknown') AS t FROM {p('sum_central')} ORDER BY t"
    ).t.tolist()
    c1, c2 = st.columns(2)
    pick_types = c1.multiselect("Organisation type", types, default=types)
    sort = c2.selectbox(
        "Rank by", ["single_bid_pct", "awards", "total_value", "n_vendors"], index=0
    )
    tlist = ",".join("'" + t.replace("'", "''") + "'" for t in pick_types) or "''"
    sc = q(
        f"SELECT org_id, org_name, coalesce(org_type,'Unknown') AS org_type, awards, "
        f"value_disclosed_pct, total_value, round(total_value/1e7, 2) AS total_value_cr, "
        f"single_bid_pct, n_units, n_vendors FROM {p('sum_central')} "
        f"WHERE coalesce(org_type,'Unknown') IN ({tlist}) ORDER BY {sort} DESC LIMIT 400"
    )
    st.dataframe(
        sc.drop(columns=["org_id", "total_value"]), width="stretch", hide_index=True,
        column_config={
            "total_value_cr": st.column_config.NumberColumn("Total value (₹ Cr)", format="%.2f"),
            "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
            "value_disclosed_pct": st.column_config.NumberColumn("Value disclosed %", format="%.1f"),
        },
    )
    st.download_button(
        "⬇ Download central summary (CSV)", sc.drop(columns=["org_id"]).to_csv(index=False).encode(),
        "central_summary.csv", "text/csv",
    )

    # ---- single-bid % by organisation type ----
    st.markdown("**Single-bid % by organisation type**")
    ot = q(
        f"SELECT coalesce(org_type,'Unknown') AS org_type, sum(awards) AS awards, "
        f"sum(awards*single_bid_pct/100.0) AS sb FROM {p('sum_central')} "
        f"GROUP BY 1 HAVING sum(awards) > 0 ORDER BY awards DESC"
    )
    ot["single_bid_pct"] = (100.0 * ot["sb"] / ot["awards"]).round(1)
    figot = px.bar(
        ot, x="org_type", y="single_bid_pct",
        labels={"org_type": "", "single_bid_pct": "Single-bid %"},
        color_discrete_sequence=["#c0392b"],
    )
    figot.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=320)
    st.plotly_chart(figot, use_container_width=True)
    st.caption(
        "Single-bid share by type of central body (reliable for all, unlike value, "
        "which many public sector undertakings do not disclose). Pre-deduplication."
    )

    st.markdown("---")
    st.subheader("Organisation → sub-units")
    if len(sc):
        org_pick = st.selectbox("Select organisation", sc.org_name.tolist())
        orow = sc[sc.org_name == org_pick].iloc[0]
        oid = orow.org_id
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Awards", f"{int(orow.awards):,}")
        m2.metric("Total value", cr(orow.total_value) if orow.value_disclosed_pct > 50 else "not disclosed")
        m3.metric("Single-bid %", f"{orow.single_bid_pct:.1f}%")
        m4.metric("Sub-units", f"{int(orow.n_units):,}")
        st.caption(
            f"Type: {orow.org_type} · value disclosed on {orow.value_disclosed_pct:.1f}% "
            f"of awards · {int(orow.n_vendors):,} distinct vendors"
        )

        units = q(
            f"SELECT sub_unit, awards, round(total_value/1e7, 2) AS value_cr, "
            f"single_bid_pct, n_vendors FROM {p('sum_central_unit')} "
            f"WHERE org_id = '{oid}' ORDER BY awards DESC LIMIT 500"
        )
        if len(units):
            st.markdown("**Sub-units** (top 500 by awards)")
            st.dataframe(
                units, width="stretch", hide_index=True,
                column_config={
                    "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.2f"),
                    "single_bid_pct": st.column_config.NumberColumn("Single-bid %", format="%.1f"),
                },
            )
            st.download_button(
                "⬇ Download sub-units (CSV)", units.to_csv(index=False).encode(),
                "central_subunits.csv", "text/csv",
            )
        else:
            st.caption("This organisation has no sub-unit breakdown, showing all its awards.")

        ALL_ORG = "All awards for this organisation"
        pick_u = st.selectbox(
            "Show awards for", [ALL_ORG] + (units.sub_unit.tolist() if len(units) else [])
        )
        if pick_u == ALL_ORG:
            aw = q(
                f"SELECT a.award_year AS year, a.title, a.winner_name_raw AS winner, "
                f"round(a.contract_value_inr/1e7, 3) AS value_cr, a.bids_received AS bids, "
                f"fl.risk_score, a.portal_id "
                f"FROM {p('fact_award')} a LEFT JOIN {p('flag_award')} fl USING (internal_id) "
                f"WHERE a.org_id = '{oid}' "
                f"ORDER BY a.contract_value_inr DESC NULLS LAST LIMIT 300"
            )
        else:
            su = pick_u.replace("'", "''")
            aw = q(
                f"SELECT a.award_year AS year, a.title, a.winner_name_raw AS winner, "
                f"round(a.contract_value_inr/1e7, 3) AS value_cr, a.bids_received AS bids, "
                f"fl.risk_score, a.portal_id "
                f"FROM {p('central_award')} ca JOIN {p('fact_award')} a USING (internal_id) "
                f"LEFT JOIN {p('flag_award')} fl USING (internal_id) "
                f"WHERE a.org_id = '{oid}' AND ca.sub_unit = '{su}' "
                f"ORDER BY a.contract_value_inr DESC NULLS LAST LIMIT 300"
            )
        st.dataframe(
            aw, width="stretch", hide_index=True,
            column_config={
                "value_cr": st.column_config.NumberColumn("Value (₹ Cr)", format="%.3f"),
                "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
            },
        )
        st.download_button(
            "⬇ Download these awards (CSV)", aw.to_csv(index=False).encode(),
            "central_awards.csv", "text/csv",
        )


# --------------------------------------------------------------- Data Quality
elif page == "Data Quality":
    st.subheader("Data quality: contract-value anomalies")
    st.markdown(
        "Some awards carry contract values that are implausible or contain placeholder "
        "digits (for example `12345678`). These almost certainly reflect data-entry "
        "mistakes on the **source CPPP portal**. They are **not** real contract amounts "
        "and imply **no wrongdoing** by any office or vendor. We list them here so the "
        "errors are visible rather than hidden, and the high-confidence junk is kept out "
        "of every total elsewhere on this site."
    )

    vq = q(f"SELECT value_quality, n, sum_value FROM {p('sum_value_quality')}")
    by_tier = dict(zip(vq.value_quality, vq.n))
    total_awards = int(vq.n.sum())
    n_excluded = int(by_tier.get("junk_magnitude", 0) + by_tier.get("junk_sequence", 0))
    n_review = int(by_tier.get("review", 0))
    n_suspect = int(by_tier.get("suspect_placeholder", 0))

    c1, c2, c3 = st.columns(3)
    c1.metric("Excluded as junk", f"{n_excluded:,}",
              f"{100*n_excluded/total_awards:.3f}% of awards")
    c2.metric("Flagged for review", f"{n_review:,}")
    c3.metric("Suspect placeholders", f"{n_suspect:,}")
    st.caption(
        f"Junk values are excluded from all money totals on this site "
        f"({n_excluded:,} of {total_awards:,} awards). Review and suspect values are "
        "kept in totals and shown here for transparency."
    )

    tiers = ["junk_magnitude", "junk_sequence", "review", "suspect_placeholder"]
    pick = st.multiselect(
        "Show tiers",
        tiers, default=tiers,
        format_func=lambda t: VQ_LABEL.get(t, t),
    )
    only_seq = st.checkbox("Only placeholder-sequence values (12345678 / 1234567)", value=False)

    for t in pick:
        st.caption(f"**{VQ_LABEL.get(t, t)}** ({VQ_KEEP_NOTE.get(t, '')})")
    tlist = ",".join("'" + t + "'" for t in pick) or "''"
    seq_clause = " AND seq_signature" if only_seq else ""
    df = q(
        f"SELECT value_quality, portal_id, contract_value_raw AS raw_value, "
        f"round(contract_value_inr/1e7, 3) AS parsed_value_cr, seq_signature, "
        f"org_name, winner, contract_at AS award_date, award_year "
        f"FROM {p('sum_value_anomaly')} "
        f"WHERE value_quality IN ({tlist}){seq_clause} "
        f"ORDER BY value_quality, contract_value_inr DESC NULLS LAST"
    )
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "value_quality": st.column_config.TextColumn("Tier"),
            "raw_value": st.column_config.TextColumn("Raw value (as stored)"),
            "parsed_value_cr": st.column_config.NumberColumn("Parsed (₹ Cr)", format="%.3f"),
            "seq_signature": st.column_config.CheckboxColumn("Placeholder seq."),
            "portal_id": st.column_config.TextColumn("Tender ID / Ref No"),
        },
    )
    st.caption(
        f"{len(df):,} records shown. Verify any record on the source portal by its "
        "Tender ID (see the sidebar). The raw value is shown exactly as stored; it is "
        "never silently corrected."
    )
    st.download_button(
        "⬇ Download these anomalies (CSV)", df.to_csv(index=False).encode(),
        "value_anomalies.csv", "text/csv",
    )


# --------------------------------------------------------------- Methodology
elif page == "Methodology":
    st.subheader("Methodology and limitations")
    st.markdown(
        "This page explains, in plain language, what Tender Watch is, where its data "
        "comes from, exactly how each flag is computed, and what the data cannot tell "
        "you. Read it before drawing any conclusion from a figure on this site."
    )

    st.success(
        "**The one rule.** Every flag is a **statistical indicator**, not an accusation "
        "of wrongdoing. A flag marks a contract that is worth a closer human look, "
        "nothing more. There are routine, innocent explanations for almost every flag. "
        "Verify against the original record before reporting anything."
    )

    # live headline numbers so this page stays correct after a rebuild
    o = q(f"SELECT * FROM {p('sum_overview')}").iloc[0]
    matched = int(q(
        f"SELECT count(*) AS m FROM {p('fact_award')} WHERE tender_id IN "
        f"(SELECT tender_id FROM {p('fact_tender')} WHERE tender_id IS NOT NULL AND tender_id <> '')"
    ).iloc[0].m)
    match_pct = 100 * matched / int(o.total_awards)

    st.markdown("### What this is")
    st.markdown(
        f"Tender Watch cleans India's Central Public Procurement Portal (CPPP) data "
        f"once and makes it searchable. It currently covers **{int(o.total_awards):,} "
        f"awards** and **{int(o.total_tenders):,} tender notices**, mapped to "
        f"**{int(o.total_orgs):,} organisations** and **{int(o.total_vendors):,} "
        f"distinct winners**. The aim is to remove the tedium of finding patterns "
        f"across millions of records, so journalists, researchers, lawyers, and "
        f"citizens can ask who keeps winning, with how much competition, from whom."
    )

    st.markdown("### Where the data comes from")
    st.markdown(
        "- The source is **two scraped databases** (one of awards, one of tender "
        "notices), a public mirror of the CPPP portal at "
        "[tender.sarthaksidhant.com](https://tender.sarthaksidhant.com/). It is a "
        "static snapshot, not a live feed.\n"
        "- Company identity comes from the **Ministry of Corporate Affairs (MCA)** "
        "registered company list (name, CIN, status, incorporation date, paid-up "
        "capital, state).\n"
        "- All of it is public information published by the Government of India. The "
        "MCA email field is personal data and is never shown or republished here."
    )

    st.markdown("### How a record is cleaned")
    st.markdown(
        "The raw data is messy: values stored as text with an escaped rupee symbol, "
        "HTML noise, JSON blobs, and one organisation split across hundreds of rows. "
        "The pipeline does the following once:\n\n"
        "- **Types every field**: contract values, deposits, fees, bid counts, and "
        "dates become real numbers and dates instead of text.\n"
        "- **Collapses the organisation hierarchy**: a body split by its sub-unit "
        "chain (for example Military Engineer Services appearing as hundreds of "
        "offices) is rolled up to the top-level body, and known spelling variants "
        "(for example Telegana and Telangana) are merged.\n"
        "- **Resolves winners**: legal-form words (Pvt, Ltd, the M/s prefix) are "
        "stripped to a normalised key so the same firm is not counted as many. This "
        "is **deterministic only**, so repeat-winner counts are a lower bound.\n"
        "- **Builds a searchable identifier** (`portal_id`): the standard CPPP Tender "
        "ID where valid, otherwise the Reference Number."
    )

    st.markdown("### What each flag means and exactly how it is computed")
    st.markdown(
        "Flags fall into two groups. **Intrinsic** flags can be computed for every "
        f"award. **Notice-linked** flags need the award to be matched to its tender "
        f"notice, which is only possible for about **{match_pct:.0f}%** of awards, so "
        "those flags cover only that subset and **under-state reality**."
    )
    st.markdown(
        "| Flag | Plain meaning | Exact rule | Coverage | Risk weight |\n"
        "|---|---|---|---|---|\n"
        "| Single bid | Only one bidder competed | bids received = 1 | Intrinsic (all awards) | 3 |\n"
        "| Zero bids | No bid count recorded | bids received = 0 | Intrinsic (all awards) | 2 |\n"
        "| Value suspect | Contract value missing or implausible | value is null, under 100, or over 1,000 crore | Intrinsic (all awards) | not scored |\n"
        "| Short window | Little time to prepare a bid | fewer than 7 days from publication to bid close | Notice-linked | 2 |\n"
        "| Low EMD | Deposit unusually small for the size | value over 10 lakh and deposit under 0.5% of value | Notice-linked | 2 |\n"
        "| High fee | Costly tender document | tender document fee over 10,000 rupees | Notice-linked | 1 |\n"
        "| Corrigendum | Tender amended after publication | the notice carries a corrigendum | Notice-linked | 1 |"
    )
    st.markdown(
        "The **risk score** is the weighted sum of the flags above (single bid and "
        "zero bids are mutually exclusive, so the practical maximum is 9). It is "
        "computed in a null-safe way: an unmatched notice cannot blank out the score. "
        "**Value suspect is a data-quality marker and does not add to the risk score.**"
    )

    st.markdown("### Vendor concentration (HHI)")
    st.markdown(
        "The Departments page shows a Herfindahl-Hirschman Index (HHI) for each "
        "organisation. It is the sum of the squared shares of each vendor in that "
        f"organisation's awards, on a 0 to 10000 scale: above {HHI_HIGH} is highly "
        f"concentrated, {HHI_MOD} to {HHI_HIGH} is moderate, below {HHI_MOD} is "
        "unconcentrated. It describes market "
        "structure, that is how much of a buyer's work goes to a few vendors, and is not a "
        "statement about the conduct of any vendor or official.\n\n"
        "Two versions are shown. **HHI (count)** uses each vendor's share of the number of "
        "awards. **HHI (value)** uses each vendor's share of the rupees, computed only over "
        "the awards that have a disclosed value, so it is blank or thin for bodies that do "
        "not publish contract values (the **Value disclosed %** column shows how much it "
        "rests on). The two can differ: one very large contract can dominate by value while "
        "barely moving the count.\n\n"
        "Two cautions apply to both. An organisation with very few awards scores high "
        "automatically, so raise the minimum award count before reading it. And because "
        "vendor names are matched deterministically, unmerged name variants split shares, "
        "so the HHI shown here is a **lower bound** on the true concentration."
    )

    st.markdown("### Timing (fiscal year-end clustering)")
    st.markdown(
        "The Overview shows the distribution of awards across calendar months. India's "
        "financial year ends on 31 March, and a concentration of awards toward year-end "
        "(January to March), with a dip just after in April, is a recognised budget-flush "
        "pattern: budget that must be spent before it lapses, awarded with less time for "
        "scrutiny. It is shown as context, by the month the contract was awarded; awards "
        "with no recorded date are excluded."
    )

    st.markdown("### About the corporate identity card (MCA match)")
    st.markdown(
        "On a vendor profile you may see a corporate identity card. Treat it with "
        "care:\n\n"
        "- The match is **by company name only**, and exact. It is shown **only when "
        "the name is unambiguous** (a single MCA company carries it). Ambiguous names "
        "are hidden to avoid misattribution.\n"
        "- It is labelled a **likely match to verify**, never a confirmed link. Many "
        "winners are individuals or proprietorships that are not in MCA at all.\n"
        "- **Company status is a present-day snapshot with no strike-off date.** A "
        "company shown as struck off today does **not** prove it was inactive when it "
        "won. It is context, not proof.\n"
        "- Notes such as won before incorporation, or within a year of it, are **neutral "
        "information**, not red flags. The usual innocent explanation is an earlier "
        "proprietorship of the same name, or an imprecise match.\n"
        "- **Fuzzy name matching is deliberately not used**, because it is the main "
        "source of false positives, which carry real defamation risk."
    )

    st.markdown("### Known limitations to keep in mind")
    st.markdown(
        f"- **Award-to-notice linkage is about {match_pct:.0f}%.** The notice-linked "
        "flags (short window, low EMD, high fee, corrigendum) and the upper risk-score "
        "range apply only to matched awards, so their totals are a lower bound.\n"
        "- **Value is missing or zero for many public sector undertakings** (for "
        "example BHEL). These are flagged as value suspect and excluded from value "
        "totals and rankings, but kept for competition analysis. A value-disclosed "
        "percentage is shown so a reporting gap is never mistaken for a real zero.\n"
        "- **Vendor resolution is deterministic only.** Repeat-winner counts are a "
        "lower bound, because a fuzzy pass would merge more name variants.\n"
        "- **Identifiers vary.** About 76% of awards carry a standard CPPP Tender ID. "
        "The rest fall back to the Reference Number, and a small share have no usable "
        "identifier.\n"
        "- **Some scraped fields show column misalignment** (about 6% of awards), "
        "which is flagged rather than dropped.\n"
        "- **The source contained duplicate records** (the same award scraped more than "
        "once, about 30% of rows). These are de-duplicated in the pipeline, so the counts "
        "here reflect distinct awards. A small residue (under 1%) of near-duplicates with "
        "blank or missing identifiers is kept on purpose, to avoid wrongly merging "
        "genuinely separate awards, so totals may still be very slightly overstated.\n"
        "- **Only the winner is known**, not the full list of bidders, so co-bidding "
        "or bid-rotation analysis is not possible from this data."
    )

    st.markdown("### How to verify a record yourself")
    st.markdown(
        "Deep links to individual award pages on the portal are signed and expire, so "
        "they cannot be permalinked. The identifier shown on each row is one of two "
        "kinds, and they verify differently:\n\n"
        "- A **standard CPPP Tender ID** (for example `2021_NTPC_123456_1`) can be "
        "searched on the official portal:\n"
        "    - Award of Contract (AOC) results: "
        "[eprocure.gov.in result of tenders](https://eprocure.gov.in/cppp/resultoftendersnew/mmpdata)\n"
        "    - Tenders: "
        "[eprocure.gov.in tender search](https://eprocure.gov.in/cppp/tendersearch/cpppdata/)\n"
        "- A **reference number** (for example `4000xxxxxx`) is an internal identifier used "
        "by many public sector bodies such as NTPC, which run their own procurement "
        "portals. The central portal has **no reference-number search field**, so these "
        "records cannot be looked up there by their number. To verify one of these, find "
        "it on the data source mirror "
        "([tender.sarthaksidhant.com](https://tender.sarthaksidhant.com/)), search by the "
        "**title and organisation** (and date), or check the relevant body's own portal.\n\n"
        "About 76% of awards carry a standard Tender ID; the rest carry only a reference "
        "number."
    )

    st.markdown("### Licensing, attribution, and data handling")
    st.markdown(
        "- **Code:** released under the MIT License.\n"
        "- **Procurement data:** from India's CPPP portal (eprocure.gov.in), used here "
        "via the public mirror at "
        "[tender.sarthaksidhant.com](https://tender.sarthaksidhant.com/). Snapshot dated "
        "26 June 2026.\n"
        "- **Company data:** Ministry of Corporate Affairs (MCA) company master data, "
        "from [data.gov.in](https://www.data.gov.in/) under the Government Open Data "
        "License India (GODL-India), which requires attribution. The MCA email field is "
        "personal data and is never displayed or published by this tool."
    )

    st.markdown("### Disclaimer and corrections")
    st.warning(
        "**This tool does not accuse anyone of anything.** Flags are statistical "
        "indicators, not findings of fact. The content is not legal, financial, or "
        "professional advice. There are routine, lawful explanations for almost every "
        "flag. Verify against the official record before relying on or reporting "
        "anything."
    )
    st.markdown(
        "If you are an affected party, or you spot an error, you can ask for a "
        "correction or removal by opening an issue on the project repository: "
        "[github.com/abcde-stack/tender-watch/issues]"
        "(https://github.com/abcde-stack/tender-watch/issues). Include the Tender ID or "
        "Reference Number and what you believe is wrong. GitHub issues are public, so "
        "please do not post sensitive personal information there. The full disclaimer "
        "and corrections policy is in `DISCLAIMER.md` in the "
        "[project repository](https://github.com/abcde-stack/tender-watch)."
    )
    st.caption(
        "If you believe a specific figure here is wrong, it is almost always traceable "
        "to the source record. Check the Tender ID or Reference Number on the portal "
        "before acting on anything."
    )
