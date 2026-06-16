"""Send the digest and fact-check report via Resend."""

import re
import resend


# ---------------------------------------------------------------------------
# Minimal Markdown → HTML converter (no external dependencies)
# ---------------------------------------------------------------------------

def _md_inline(text: str) -> str:
    """Convert inline markdown (bold, italic, code, links) to HTML."""
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code style='background:#f4f4f4;padding:1px 4px;border-radius:3px'>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def markdown_to_html(md: str) -> str:
    """Convert a Markdown string to a clean HTML fragment."""
    lines = md.split("\n")
    html: list[str] = []
    in_table = False
    table_header_done = False
    in_code_block = False
    paragraph_lines: list[str] = []

    def flush_paragraph():
        if paragraph_lines:
            content = " ".join(paragraph_lines).strip()
            if content:
                html.append(f"<p>{_md_inline(content)}</p>")
            paragraph_lines.clear()

    for line in lines:
        # Code blocks
        if line.startswith("```"):
            flush_paragraph()
            if not in_code_block:
                html.append("<pre style='background:#f4f4f4;padding:12px;border-radius:4px;overflow-x:auto'><code>")
                in_code_block = True
            else:
                html.append("</code></pre>")
                in_code_block = False
            continue

        if in_code_block:
            html.append(line.replace("<", "&lt;").replace(">", "&gt;"))
            continue

        # Tables
        if "|" in line:
            stripped = line.strip()
            if re.match(r"^\|[-| :]+\|$", stripped):
                # Separator row — close thead, open tbody
                html.append("</thead><tbody>")
                table_header_done = True
                continue
            if not in_table:
                flush_paragraph()
                html.append(
                    "<table style='border-collapse:collapse;width:100%;margin:12px 0;font-size:14px'>"
                    "<thead>"
                )
                in_table = True
                table_header_done = False
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            tag = "th" if not table_header_done else "td"
            style = (
                "style='border:1px solid #ddd;padding:6px 10px;text-align:left;"
                + ("background:#f8f9fa;font-weight:bold'" if tag == "th" else "'")
            )
            row = "".join(f"<{tag} {style}>{_md_inline(c)}</{tag}>" for c in cells)
            html.append(f"<tr>{row}</tr>")
            continue

        if in_table:
            html.append("</tbody></table>")
            in_table = False
            table_header_done = False

        # Horizontal rule
        if re.match(r"^-{3,}$", line.strip()):
            flush_paragraph()
            html.append("<hr style='border:none;border-top:1px solid #e0e0e0;margin:20px 0'>")
            continue

        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush_paragraph()
            level = len(m.group(1))
            sizes = {1: "24px", 2: "20px", 3: "17px", 4: "15px"}
            margins = {1: "24px 0 8px", 2: "20px 0 6px", 3: "16px 0 4px", 4: "12px 0 4px"}
            html.append(
                f"<h{level} style='font-size:{sizes[level]};margin:{margins[level]};color:#1a1a2e'>"
                f"{_md_inline(m.group(2))}</h{level}>"
            )
            continue

        # List items
        if re.match(r"^[-*]\s+", line):
            flush_paragraph()
            content = re.sub(r"^[-*]\s+", "", line)
            html.append(f"<li style='margin:4px 0'>{_md_inline(content)}</li>")
            continue

        # Empty line → paragraph break
        if not line.strip():
            flush_paragraph()
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    if in_table:
        html.append("</tbody></table>")
    if in_code_block:
        html.append("</code></pre>")

    return "\n".join(html)


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Georgia,serif;color:#333">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:24px 16px">
<table width="100%" style="max-width:720px;background:#fff;border-radius:8px;
       box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden">

  <!-- Header banner -->
  <tr><td style="background:#1a1a2e;padding:28px 32px">
    <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:1px;text-transform:uppercase">
      Daily Research Digest</p>
    <h1 style="margin:6px 0 0;font-size:22px;color:#fff;line-height:1.3">{category}</h1>
    <p style="margin:6px 0 0;font-size:13px;color:#aaaacc">{month_year}</p>
  </td></tr>

  <!-- Digest body -->
  <tr><td style="padding:32px">
    {digest_html}
  </td></tr>

  <!-- Fact-check section -->
  <tr><td style="background:#fffbf0;border-top:3px solid #e8a317;padding:32px">
    <h2 style="margin:0 0 16px;font-size:18px;color:#7a4f00">🔍 Fact-Check Report</h2>
    {fact_check_html}
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f8f8f8;padding:16px 32px;border-top:1px solid #eee">
    <p style="margin:0;font-size:11px;color:#999;line-height:1.6">
      Generated automatically from PubMed data using the Claude API.
      Abstracts sourced from the National Library of Medicine (NLM/NCBI).
      This digest is for informational purposes only and does not constitute medical advice.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""


def send_digest_email(
    to_email: str,
    from_email: str,
    category: str,
    month_year: str,
    digest_content: str,
    fact_check_content: str,
    resend_api_key: str,
) -> None:
    """Send digest + fact-check report via Resend."""
    resend.api_key = resend_api_key

    digest_html = markdown_to_html(digest_content)
    fact_check_html = markdown_to_html(fact_check_content)

    subject = f"Research Digest: {category} — {month_year}"

    html_body = _EMAIL_TEMPLATE.format(
        subject=subject,
        category=category,
        month_year=month_year,
        digest_html=digest_html,
        fact_check_html=fact_check_html,
    )

    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    resend.Emails.send(params)
