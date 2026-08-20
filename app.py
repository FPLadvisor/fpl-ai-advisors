import os, math, requests, pandas as pd, streamlit as st
from datetime import datetime, timezone

BASE = os.getenv("FPL_API_BASE", "https://fantasy.premierleague.com/api").rstrip("/")
DEFAULT_TEAM_ID = os.getenv("FPL_TEAM_ID", "1643829")
TIMEOUT = 20

st.set_page_config(page_title="FPL AI Command Center", page_icon="⚽", layout="wide")

@st.cache_data(ttl=300)
def get_json(path):
    r = requests.get(f"{BASE}/{path.lstrip('/')}", timeout=TIMEOUT,
                     headers={"User-Agent":"FPL-AI-Advisor/3.0"})
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300)
def bootstrap():
    return get_json("bootstrap-static/")

@st.cache_data(ttl=300)
def fixtures():
    return get_json("fixtures/")

def player_df():
    b = bootstrap()
    teams = {t["id"]: t["name"] for t in b["teams"]}
    pos = {p["id"]: p["singular_name"] for p in b["element_types"]}
    rows=[]
    for p in b["elements"]:
        rows.append({
            "id":p["id"], "name":p["web_name"], "full_name":f'{p["first_name"]} {p["second_name"]}',
            "team":teams[p["team"]], "team_id":p["team"], "position":pos[p["element_type"]],
            "price":p["now_cost"]/10, "xP":float(p["ep_next"] or 0), "form":float(p["form"] or 0),
            "ownership":float(p["selected_by_percent"] or 0), "minutes":p["minutes"],
            "status":p["status"], "news":p["news"], "chance":p["chance_of_playing_next_round"],
            "ict":float(p["ict_index"] or 0), "bps":p["bps"],
            "in":p["transfers_in"], "out":p["transfers_out"], "points":p["total_points"],
            "goals":p["goals_scored"], "assists":p["assists"], "cs":p["clean_sheets"]
        })
    return pd.DataFrame(rows)

def current_gw():
    for e in bootstrap()["events"]:
        if e.get("is_current"): return e["id"]
    for e in bootstrap()["events"]:
        if e.get("is_next"): return e["id"]
    return 1

def team_summary(team_id):
    return get_json(f"entry/{int(team_id)}/")

def manager_picks(team_id, gw):
    return get_json(f"entry/{int(team_id)}/event/{int(gw)}/picks/")

def availability(row):
    if row["status"] == "a": return 1.0
    if row["chance"] is None: return 0.45
    return max(0.0, min(row["chance"]/100, 1.0))

def base_score(row):
    return (row["xP"]*.65 + row["form"]*.12 +
            math.log1p(max(row["ict"],0))*.07 +
            math.log1p(max(row["bps"],0))*.03 +
            min(row["ownership"],100)*.01) * availability(row)

def captain_score(row):
    return (row["xP"]*.72 + row["form"]*.08 +
            math.log1p(max(row["ict"],0))*.06 +
            min(row["ownership"],100)*.02) * availability(row)

def fixture_adjustments(df):
    fx = pd.DataFrame(fixtures())
    if fx.empty: return df
    # Use official FDR for the next three available GWs.
    upcoming = [x["id"] for x in bootstrap()["events"] if x["id"] >= current_gw()][:3]
    rows=[]
    for _, p in df.iterrows():
        vals=[]
        for gw in upcoming:
            for _, f in fx[fx["event"].eq(gw)].iterrows():
                if f["team_h"] == p["team_id"]: vals.append(f.get("team_h_difficulty",3))
                elif f["team_a"] == p["team_id"]: vals.append(f.get("team_a_difficulty",3))
        avg = sum(vals)/len(vals) if vals else 3
        # lower FDR = easier; small transparent adjustment
        adj = max(0.80, min(1.20, 1.12 - 0.08*avg))
        rows.append(adj)
    out=df.copy()
    out["fixture_factor"]=rows
    out["3GW_xP"]=out["xP"]*3*out["fixture_factor"]*out.apply(availability,axis=1)
    out["advisor_score"]=out.apply(base_score,axis=1)*out["fixture_factor"]
    out["captain_score"]=out.apply(captain_score,axis=1)*out["fixture_factor"]
    return out

def manual_squad(df, names):
    clean=[x.strip().lower() for x in names if x.strip()]
    return df[df["name"].str.lower().isin(clean) | df["full_name"].str.lower().isin(clean)].copy()

def transfers(df, squad, bank):
    results=[]
    if squad.empty: return pd.DataFrame()
    targets=df[(~df.id.isin(squad.id)) & (df.status=="a")].copy()
    for _, out in squad.iterrows():
        t=targets[(targets.position==out.position) & (targets.price<=out.price+bank+1e-9)].copy()
        if t.empty: continue
        t["gain3"]=t["3GW_xP"]-out["3GW_xP"]
        for _, inn in t.nlargest(3,"gain3").iterrows():
            results.append({
                "OUT":out["name"],"IN":inn["name"],"Price":inn["price"],
                "3GW gain":round(inn["gain3"],2),
                "Net after -4":round(inn["gain3"]-4,2),
                "IN xP":inn["xP"],"Ownership %":inn["ownership"],
                "Hit decision":"🟢 JUSTIFIED" if inn["gain3"]>4 else ("🟡 WAIT" if inn["gain3"]>2 else "🔴 AVOID")
            })
    return pd.DataFrame(results).sort_values("3GW gain",ascending=False).head(15)

st.title("⚽ FPL AI COMMAND CENTER")
st.caption("V3 • Live public FPL data • 3-GW tactical engine • Team ID 1643829")

with st.sidebar:
    st.header("Manager Setup")
    team_id=st.text_input("FPL Team ID", DEFAULT_TEAM_ID)
    bank=st.number_input("Bank (£m)", min_value=0.0, max_value=20.0, value=1.0, step=0.1)
    free_transfers=st.number_input("Free Transfers", min_value=1, max_value=5, value=1, step=1)
    st.caption("The public FPL API does not expose private squad picks reliably without a logged-in session. To keep your password out of this app, enter your squad once below.")
    default_names=st.session_state.get("squad_names","")
    squad_text=st.text_area("Your 15 players (one per line)", default_names, height=220)
    st.session_state["squad_names"]=squad_text
    if st.button("🔄 Refresh"):
        st.cache_data.clear(); st.rerun()

df=fixture_adjustments(player_df())
gw=current_gw()

# Manager metadata
try:
    m=team_summary(team_id)
    name=m.get("name","Manager")
    rank=m.get("summary_overall_rank")
    total=m.get("summary_overall_points")
except Exception:
    name="Manager"; rank=None; total=None

# Try public/current picks; fall back gracefully.
squad=None
try:
    pk=manager_picks(team_id,gw)
    ids=[x["element"] for x in pk.get("picks",[])]
    if ids: squad=df[df.id.isin(ids)].copy()
except Exception:
    squad=None

if squad is None or len(squad)<11:
    squad=manual_squad(df,squad_text.splitlines())

c1,c2,c3,c4=st.columns(4)
c1.metric("Gameweek",gw)
c2.metric("Overall Rank", f"{rank:,}" if rank else "—")
c3.metric("Points", total if total is not None else "—")
c4.metric("Squad Loaded", f"{len(squad)}/15")

if len(squad)<15:
    st.warning("For a complete personal transfer analysis, enter all 15 players in the sidebar. Public FPL endpoints can require authentication for detailed picks.")

st.divider()

a,b=st.columns(2)
with a:
    st.subheader("👑 Captain")
    pool=squad if len(squad) else df
    caps=pool.sort_values("captain_score",ascending=False).head(5)
    if len(caps):
        st.success(f'RECOMMENDED: {caps.iloc[0]["name"]}')
        st.dataframe(caps[["name","team","xP","form","ownership","fixture_factor","captain_score"]].round(2),
                     use_container_width=True,hide_index=True)

with b:
    st.subheader("💎 Differential Watch")
    diff=df[df.ownership<=15].sort_values("advisor_score",ascending=False).head(8)
    st.dataframe(diff[["name","team","price","xP","ownership","form","3GW_xP"]].round(2),
                 use_container_width=True,hide_index=True)

st.subheader("🔄 Transfer Optimizer")
tr=transfers(df,squad,bank)
if len(tr):
    st.dataframe(tr,use_container_width=True,hide_index=True)
    best=tr.iloc[0]
    if best["3GW gain"]>0:
        st.success(f'Best 3-GW move: {best["OUT"]} → {best["IN"]} | +{best["3GW gain"]} projected points')
else:
    st.info("Enter your 15-player squad to generate transfer recommendations.")

st.subheader("📊 Best Players by 3-GW Outlook")
best=df.sort_values("3GW_xP",ascending=False).head(15)
st.dataframe(best[["name","team","position","price","xP","3GW_xP","ownership","form","news"]].round(2),
             use_container_width=True,hide_index=True)

st.subheader("🚨 Risk Watch")
risk=df[(df.status!="a") | (df.chance.fillna(100)<75) | (df.news!="")].copy()
if len(risk):
    st.dataframe(risk[["name","team","status","chance","news","ownership"]].head(20),
                 use_container_width=True,hide_index=True)
else:
    st.success("No major availability flags in the current public data.")

st.caption("Data refreshes automatically from the public FPL API every 5 minutes while the app is being used. This is decision support, not a guarantee of points.")
