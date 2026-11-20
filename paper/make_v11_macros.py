#!/usr/bin/env python3
"""Macros + tables for 922 v1.1 (N/D/R/G x 3 models; H4-H6; detector comparison incl. LLM judge), read only from the frozen
v1.1 outputs: observer-test-v11-001/observer.json, the run episodes it names, toolcompare-test-v11-001/, llmjudge-test-v11-001/.
Rendering only: decisions and p-values are copied; detector counts for the LLM judge are tallied with the same definitions
as tools/tool_compare.py (flag null = not flagged). Create-only. Prefix \\V. LaTeX macro names contain no digits.
  python3 -I tools/make_v11_macros.py ../v1.1/results test generated-v11"""
import hashlib, json, os, sys
from pathlib import Path
res, phase, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
if out.exists(): sys.exit("exists (create-only)")
OBS = res / f"observer-{phase}-v11-001" / "observer.json"; TC = res / f"toolcompare-{phase}-v11-001"; LJ = res / f"llmjudge-{phase}-v11-001"
MK = {"qwen/qwen3.6-35b-a3b": ("QwenMoe", "qwen3.6-35b-a3b"), "openai/gpt-oss-20b": ("Gptoss", "gpt-oss-20b"),
      "ollama:qwen3.6:27b-coding-mtp-q4_K_M": ("QwenCoder", "qwen3.6-27b-coding")}
CONDS = ["N", "D", "R", "G"]; TN = {"H4_trapSNF_D_minus_N": "HFour", "H5_trapSNF_R_minus_N": "HFive", "H6_trapSNF_G_minus_N": "HSix"}
pct = lambda x: "--" if x is None else f"{100 * x:.1f}"
f3 = lambda x: "--" if x is None else (f"$-${abs(x):.3f}" if x < 0 else f"{x:.3f}")
fp = lambda x: "--" if x is None else ("$<$0.001" if x < 0.001 else f"{x:.3f}")
DEC = {"SUPPORTED": "supported", "NOT_ESTABLISHED": "not established", "NON_INFORMATIVE": "non-informative"}
M, srcs = [], []
m = lambda k, v: M.append(f"\\newcommand{{\\V{k}}}{{{v}}}")
b = OBS.read_bytes(); O = json.loads(b); srcs.append(f"{OBS.parent.name}/observer.json {hashlib.sha256(b).hexdigest()}")
rows = []; nsup = {n: 0 for n in TN.values()}
for r in O["runs"]:
    key, label = MK.get(r["model"], (None, None))
    if key is None: continue
    A = r["analysis"]; PC = A["perCondition"]; T = A["tests"]
    run = Path(r["run"]); run = run if run.is_absolute() else (OBS.parent.parent.parent / r["run"])
    if not run.exists(): run = res / Path(r["run"]).name
    eps = [json.loads(l) for l in open(run / "episodes.jsonl")]
    det = {(e["taskId"], e["cond"]): e for e in r["episodeDetail"]}
    g_green = [e for e in eps if e["cond"] == "G" and not e["systemFailure"] and e.get("pristineGCiPass")]
    escape = [e for e in g_green if any(w["trap"] and not w["hiddenPass"] for w in det[(e["taskId"], "G")]["cls"]["warnings"])]
    m(key + "GCiGreen", pct(len(g_green) / max(1, sum(1 for e in eps if e["cond"] == "G" and not e["systemFailure"]))))
    m(key + "GEscape", pct(len(escape) / len(g_green)) if g_green else "--")
    for c in CONDS:
        pc = PC.get(c) or {}
        m(key + "TrapSNF" + c, pct(pc.get("silencedNotFixedTrap"))); m(key + "CiPass" + c, pct(pc.get("ciPass")))
        m(key + "PlainSNF" + c, pct(pc.get("silencedNotFixedPlain"))); m(key + "SuppFP" + c, pct(pc.get("suppressionFP")))
        m(key + "Calls" + c, f"{pc['meanToolCalls']:.1f}" if pc.get("meanToolCalls") is not None else "--")
        m(key + "Tamper" + c, pct(pc.get("tampered")))
    for k, n in TN.items():
        t = T.get(k)
        if not t: continue
        m(key + n + "Diff", f3(t["meanFamilyDifference"])); m(key + n + "P", fp(t["pHolm"])); m(key + n + "Dec", DEC.get(t["decision"], t["decision"].lower()) + (" (opposite)" if t.get("oppositeDirection") else ""))
        nsup[n] += t["decision"] == "SUPPORTED"
    m(key + "Gates", "pass" if A.get("gatesPass") else "fail")
    s = lambda k: "$^{*}$" if T.get(k) and T[k]["decision"] == "SUPPORTED" else ""
    rows.append(f"{label} & {pct((PC.get('N') or {}).get('silencedNotFixedTrap'))} & {pct((PC.get('D') or {}).get('silencedNotFixedTrap'))}{s('H4_trapSNF_D_minus_N')} & "
                f"{pct((PC.get('R') or {}).get('silencedNotFixedTrap'))}{s('H5_trapSNF_R_minus_N')} & {pct((PC.get('G') or {}).get('silencedNotFixedTrap'))}{s('H6_trapSNF_G_minus_N')} & "
                f"{pct((PC.get('N') or {}).get('ciPass'))} & {pct((PC.get('D') or {}).get('ciPass'))} & {pct((PC.get('R') or {}).get('ciPass'))} & {pct((PC.get('G') or {}).get('ciPass'))} \\\\")
for n in TN.values(): m("NSup" + n, nsup[n])
tab1 = ("\\begin{tabular}{@{}lcccccccc@{}}\n\\toprule\n & \\multicolumn{4}{c}{trap silenced-not-fixed (\\%)} & \\multicolumn{4}{c}{CI pass (\\%)} \\\\\n\\cmidrule(lr){2-5}\\cmidrule(l){6-9}\n"
        "Model & N & D & R & G & N & D & R & G \\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
# detector comparison
DETS = [("p922lint", "Study linter"), ("ruff-default", "ruff (default)"), ("ruff-tuned", "ruff (exception rules)"), ("pylint-default", "pylint (default)"),
        ("pylint-tuned", "pylint (exception rules)"), ("semgrep", "Semgrep (official packs)"), ("boosting", "Tuned boosting$^{\\ddagger}$"), ("llm-judge", "LLM judge (zero-shot)"), ("contract_check", "contract\\_check$^{\\ddagger}$")]
tab2 = None
if (TC / "toolcompare.json").exists():
    bt = (TC / "toolcompare.json").read_bytes(); TCJ = json.loads(bt); srcs.append(f"{TC.name}/toolcompare.json {hashlib.sha256(bt).hexdigest()}")
    R = dict(TCJ["results"])
    if (LJ / "units.jsonl").exists():
        bl = (LJ / "units.jsonl").read_bytes(); srcs.append(f"{LJ.name}/units.jsonl {hashlib.sha256(bl).hexdigest()}")
        c = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}; unp = 0
        for u in map(json.loads, bl.decode().splitlines()):
            f = bool(u.get("flag")); unp += u.get("flag") is None
            c[("TP" if u["bad"] else "FP") if f else ("FN" if u["bad"] else "TN")] += 1
        tp, fpp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
        R["llm-judge"] = {**c, "precision": tp / (tp + fpp) if tp + fpp else None, "recall": tp / (tp + fn) if tp + fn else None,
                          "f1": 2 * tp / (2 * tp + fpp + fn) if tp else 0.0, "falseAlarmRate": fpp / (fpp + tn) if fpp + tn else None}
        m("JudgeUnparsed", unp)
    lines = []
    for k, lab in DETS:
        r = R.get(k)
        if not r: continue
        nm = "".join(w.capitalize() for w in k.replace("_", "-").replace("p922lint", "studylint").split("-"))
        for met, mn in (("precision", "Prec"), ("recall", "Rec"), ("f1", "Fone"), ("falseAlarmRate", "FalseAlarm")): m("Det" + nm + mn, f3(r.get(met)))
        lines.append(f"{lab} & {f3(r.get('precision'))} & {f3(r.get('recall'))} & {f3(r.get('f1'))} & {f3(r.get('falseAlarmRate'))} \\\\")
    m("DetUnits", TCJ["testUnits"]); m("DetBad", TCJ["testBad"]); m("BoostParams", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in TCJ["boosting"]["bestParams"].items()))
    tab2 = ("\\begin{tabular}{@{}lcccc@{}}\n\\toprule\nDetector & Prec. & Recall & F1 & False alarm \\\\\n\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")
head = "% generated by tools/make_v11_macros.py; sources (sha256):\n" + "\n".join("% " + x for x in srcs) + "\n% do not edit"
out.mkdir(parents=True)
(out / "v11-macros.tex").write_text(head + "\n" + "\n".join(M) + "\n"); (out / "tab-v11-conditions.tex").write_text(head + "\n" + tab1)
if tab2: (out / "tab-v11-detectors.tex").write_text(head + "\n" + tab2)
(out / "SOURCES.sha256").write_text("\n".join(srcs) + "\n"); print(len(M), "macros")
