"""Optional executive summary written by Gemini from the rule-based findings.

The API key is read from an environment variable only. If anything goes wrong
the report carries on without a summary.
"""
import os

from .formatting import money, pct, roas


def build_prompt(data, cfg):
    o = data.overall
    cur = cfg["currency"]
    facts = "\n".join(f"- {f}" for f in data.insights.findings)
    actions = "\n".join(f"- {r}" for r in data.insights.recommendations)
    return f"""You are writing for a marketing leadership team.
Write an executive summary of 100-130 words in plain English, as one paragraph.
Use only the numbers given below. Do not invent figures, causes or benchmarks.
Lead with the overall result, then the most important finding, then the top action.

Overall: {o['campaigns']:,} campaigns, revenue {money(o['revenue'], cur)}, spend {money(o['spend'], cur)},
ROAS {roas(o['roas'])}, ROI {pct(o['roi'], 0)}, click-through rate {pct(o['ctr'], 2)}.

Findings:
{facts}

Recommendations:
{actions}
"""


def write_summary(data, cfg):
    """Return the summary text, or None if it couldn't be produced."""
    env_var = cfg["ai"]["api_key_env"]
    key = os.environ.get(env_var)
    if not key:
        print(f"  ! --ai skipped: set the {env_var} environment variable to use it.")
        return None
    try:
        from google import genai

        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=cfg["ai"]["model"], contents=build_prompt(data, cfg)
        )
        text = (response.text or "").strip()
        return text or None
    except Exception as exc:  # network, quota, bad key - none of these should stop the report
        print(f"  ! --ai skipped: Gemini request failed ({type(exc).__name__}: {exc})")
        return None
