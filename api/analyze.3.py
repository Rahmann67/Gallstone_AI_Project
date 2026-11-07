# Runs on the server, never in the visitor's browser.
# That is why your secret API key is safe here.
# Uses only Python's built-in libraries, so nothing extra needs installing.

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

# The instructions that tell the AI how to answer
INSTRUCTIONS = """You are the analysis engine of a health information website. A visitor shared the information below.
Reply in plain text only, with no markdown symbols, using these labeled sections:
What I see; Possible explanations (most likely first, with how likely each is and what points to it);
Typical recovery time (realistic ranges and what affects them); What you can do now;
See a doctor soon if; Get emergency care now if.
Rules: never present a diagnosis as certain. If the information is not enough, say so and name the 2 or 3 details that would help most.
If anything suggests an emergency (chest pain, trouble breathing, stroke signs, heavy bleeding, thoughts of self-harm and similar),
begin with a clear instruction to contact local emergency services or a crisis line.
For lab or report values, explain what each abnormal value usually means and which matter most.
Keep it under 350 words. Finish with one line saying this is general information, not medical advice."""

# Remembers when each visitor made requests (basic protection for your bill)
request_log = {}


class handler(BaseHTTPRequestHandler):
    # Send a JSON reply back to the page
    def reply(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Only accept data sent from the page (POST)
    def do_GET(self):
        self.reply(405, {"error": "Use POST."})

    def do_POST(self):
        # Limit each visitor to 10 analyses per hour
        visitor = (self.headers.get("x-forwarded-for") or "unknown").split(",")[0].strip()
        now = time.time()
        recent = [t for t in request_log.get(visitor, []) if now - t < 3600]
        if len(recent) >= 10:
            return self.reply(429, {"error": "Too many requests. Please try again later."})
        recent.append(now)
        request_log[visitor] = recent

        # Read and check what the page sent
        length = int(self.headers.get("content-length") or 0)
        if length > 4_000_000:
            return self.reply(413, {"error": "That input is too large."})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.reply(400, {"error": "Invalid request."})

        text = str(data.get("text", ""))
        report_text = str(data.get("reportText", ""))
        image = str(data.get("image", ""))
        if len(text) > 4000 or len(report_text) > 20000 or len(image) > 3_000_000:
            return self.reply(413, {"error": "That input is too large."})
        if not text.strip() and not report_text.strip() and not image:
            return self.reply(400, {"error": "Add your symptoms or a report first."})

        # Build the message for the AI (photo first, then the text)
        content = []
        if image:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image},
            })
        message = "Symptoms and context from the visitor:\n" + (text or "(none given)")
        if report_text:
            message += "\n\nReport text:\n" + report_text
        if image:
            message += "\n\nA photo of a report is attached."
        content.append({"type": "text", "text": message})

        # Ask the Anthropic API and send the answer back to the page
        payload = {
            "model": "claude-sonnet-5-5",
            "max_tokens": 900,
            "system": INSTRUCTIONS,
            "messages": [{"role": "user", "content": content}],
        }
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            print("ANTHROPIC_API_KEY is not set")
            return self.reply(500, {"error": "The server is missing its API key."})
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,  # your secret key, set in Vercel
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            # The API answered with an error. Details go to the Vercel logs.
            print("Anthropic API error", e.code, e.read().decode("utf-8", "ignore"))
            return self.reply(502, {"error": "The analysis service returned an error (code %d). Please try again." % e.code})
        except (urllib.error.URLError, TimeoutError) as e:
            # Could not reach the API at all (connection, DNS, SSL or timeout)
            reason = str(getattr(e, "reason", e))[:120]
            print("Network error", reason)
            return self.reply(502, {"error": "The analysis service is unavailable (%s). Please try again." % reason})

        answer = "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")
        self.reply(200, {"text": answer})
