#!/usr/bin/env python3
"""
Daily Bay Area Filmmaking Job Scan
Runs via GitHub Actions, searches for SF Bay Area film jobs posted in the last
24-48 hours using Claude's web search, and emails results to the recipient list.
"""

import os
import sys
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import markdown

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RECIPIENTS = ["james@walsh.nu", "walshcben@gmail.com"]

NOW_UTC = datetime.now(timezone.utc)
DATE_DISPLAY = NOW_UTC.strftime("%B %-d, %Y")   # e.g. "May 26, 2026"
DATE_SHORT   = NOW_UTC.strftime("%Y-%m-%d")

MODEL = "claude-opus-4-8"
MAX_TOKENS = 8192
MAX_LOOP_ITERATIONS = 20   # safety cap for tool-use loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The search prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a sharp Bay Area film-industry job scout with real-time web access. "
    "You search multiple job boards, read the actual postings, and return a clean, "
    "factual summary. You never invent listings. If a site returns no relevant recent "
    "postings you say so explicitly."
)

USER_PROMPT = f"""Today is {DATE_DISPLAY}.

Search for filmmaking and film/video production jobs in the **San Francisco Bay Area** posted in the **last 24–48 hours**.

---

## Candidate snapshot
- BSc Theatre | MA Filmmaking, University of Creative Arts (UK) — completing August 2026
- MA is creative/directing-oriented (narrative, documentary, short-form)
- Target start: August–September 2026
- Level: entry-level to slightly-above entry-level (up to ~2 years experience required)

---

## Two role tracks to cover

### Volume track — entry-level, realistic
- Production Assistant / on-set crew
- Production Coordinator / Office PA
- Assistant Editor / Post-Production Coordinator
- Theatre-adjacent media roles
- Fellowships and training pipelines

### Creative track — flag even if slightly above entry-level
- Director's Assistant / Assistant to Director or Showrunner
- Development Assistant / Story Reader / Script Coordinator
- Creative Producer / Associate Producer at indie shops
- Documentary roles: field producer, AP, archival researcher
- Commercial / branded content production (small teams, broad responsibilities)
- Music video and short-form narrative production

---

## Employer categories to check
- Indie/boutique production companies — **especially Nen Creative**
- Documentary outfits: ITVS, KQED, Bay Area Video Coalition (BAVC Media), independent doc producers
- Film orgs: SFFILM, San Francisco Film Commission, CAAM
- Studios/tech-adjacent: ILM, Pixar, Tesla media team, Paramount/KPIX
- Sports/entertainment content: SF Giants, Golden State Warriors
- Commercial production houses and branded content studios

---

## Sites to search (search each one)
1. LinkedIn Jobs — search "film production" OR "production assistant" OR "production coordinator" site:linkedin.com/jobs location "San Francisco Bay Area"
2. Indeed — search "production assistant" OR "production coordinator" OR "assistant editor" "San Francisco" OR "Bay Area" film OR video
3. EntertainmentCareers.net — search for Bay Area film/video listings
4. ProductionHub — search for San Francisco / Bay Area crew and coordinator listings
5. Also check: KQED jobs page, SFFILM job board, BAVC Media job board, ILM/Lucasfilm careers

---

## Output format — no preamble, no strategy recap, just the results

**New Today**

*Volume Track*
- [Company] — [Role Title] — [URL] — [Posted date]
(If none found: "None found in the last 24–48 hours.")

*Creative Track*
- [Company] — [Role Title] — [URL] — [Posted date]
(If none found: "None found in the last 24–48 hours.")

**Nen Creative Status**
Is the Production Coordinator posting still live? Check their website and LinkedIn page.

**Standouts**
1–2 sentences flagging any role that is an especially strong fit for the MA Filmmaking background. Be specific.

**Stretch Role of the Day**
If you spotted one role requiring up to 2 years experience that aligns with the creative track, describe it here (company, title, link, why it fits). Skip this section entirely if nothing fits or if the only options require 3+ years.
"""


# ---------------------------------------------------------------------------
# Claude web-search conversation loop
# ---------------------------------------------------------------------------

def extract_text(content_blocks) -> str:
    """Pull all text out of a list of content blocks (handles SDK objects or raw dicts)."""
    parts = []
    for block in content_blocks:
        # SDK object path
        block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if block_type == "text":
            text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def collect_tool_uses(content_blocks) -> list:
    """Return all tool_use / server_tool_use blocks from a response."""
    tool_uses = []
    for block in content_blocks:
        block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if block_type in ("tool_use", "server_tool_use"):
            tool_uses.append(block)
    return tool_uses


def run_job_scan() -> str:
    """Call Claude with web search enabled and return the final text response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": "user", "content": USER_PROMPT}]

    for iteration in range(1, MAX_LOOP_ITERATIONS + 1):
        log.info("Claude API call — iteration %d", iteration)

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )

        stop_reason = response.stop_reason
        log.info("stop_reason=%s  content_types=%s", stop_reason,
                 [getattr(b, "type", "?") for b in response.content])

        # --- Final answer ---
        if stop_reason == "end_turn":
            text = extract_text(response.content)
            if text:
                log.info("Got final answer (%d chars)", len(text))
                return text
            # Occasionally end_turn arrives with no text yet — keep looping
            log.warning("end_turn but no text; continuing…")

        # --- Tool-use round ---
        tool_uses = collect_tool_uses(response.content)
        if tool_uses or stop_reason == "tool_use":
            # Append assistant turn (must include the full content list)
            messages.append({
                "role": "assistant",
                "content": response.content,
            })

            # Build tool_result stubs — Anthropic's server fills in the search
            # results when it processes the next request.
            tool_results = []
            for tu in tool_uses:
                tu_id = getattr(tu, "id", None) or (tu.get("id") if isinstance(tu, dict) else None)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu_id,
                    "content": [],   # server-side: Anthropic provides real results
                })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            continue   # go around for Claude's next reply

        # --- Max-tokens or other pause ---
        if stop_reason in ("max_tokens", "pause_turn"):
            partial = extract_text(response.content)
            log.warning("Stopped due to %s; returning partial text.", stop_reason)
            return partial or "(No output — scan hit token/pause limit.)"

        # --- Anything else ---
        log.warning("Unexpected stop_reason=%s", stop_reason)
        partial = extract_text(response.content)
        if partial:
            return partial
        break

    return "(Error: scan did not complete within the allowed number of iterations.)"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def build_html(body_md: str) -> str:
    """Wrap markdown body in a simple HTML email template."""
    body_html = markdown.markdown(
        body_md,
        extensions=["extra", "nl2br"],
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;max-width:680px;
             margin:0 auto;padding:24px;color:#222;line-height:1.5;">
  <h1 style="font-size:22px;color:#1a1a2e;border-bottom:2px solid #e8e8e8;
             padding-bottom:8px;">
    \U0001f3ac Bay Area Film Jobs &mdash; {DATE_DISPLAY}
  </h1>
  {body_html}
  <hr style="margin-top:36px;border:none;border-top:1px solid #e8e8e8;">
  <p style="font-size:11px;color:#999;">
    Automated daily scan · Claude {MODEL} · {DATE_DISPLAY}
  </p>
</body>
</html>"""


def send_email(subject: str, text_body: str, html_body: str) -> None:
    """Send a multipart email via Gmail SMTP."""
    sender   = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise EnvironmentError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Ben's Job Scout <{sender}>"
    msg["To"]      = ", ".join(RECIPIENTS)

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html",  "utf-8"))

    log.info("Connecting to Gmail SMTP…")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, RECIPIENTS, msg.as_string())
    log.info("Email delivered to %s", RECIPIENTS)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    subject = f"\U0001f3ac Bay Area Film Jobs — {DATE_DISPLAY}"

    log.info("=== Daily Bay Area Filmmaking Job Scan starting (%s) ===", DATE_DISPLAY)

    try:
        content = run_job_scan()
        html    = build_html(content)
        send_email(subject, content, html)
        log.info("=== Scan complete ✓ ===")

    except Exception as exc:
        log.exception("Scan failed: %s", exc)
        error_text = f"The daily Bay Area film job scan failed on {DATE_DISPLAY}.\n\nError:\n{exc}"
        error_html = f"<p><strong>Scan failed on {DATE_DISPLAY}</strong></p><pre>{exc}</pre>"
        try:
            send_email(f"❌ Film Job Scan Error — {DATE_DISPLAY}", error_text, error_html)
        except Exception as mail_exc:
            log.error("Could not send error email either: %s", mail_exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
