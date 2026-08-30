import resend
from ..core.config import settings
import os
from dotenv import load_dotenv
load_dotenv()

resend_key   = os.getenv("RESEND_API_KEY")
BASE_URL     = os.getenv("BASE_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Initialize Resend
resend.api_key = resend_key


def send_email(to: str, subject: str, html: str):
    """Send an email using Resend with full debug logs."""
    try:
        print("\n[EMAIL LOG] ===== START =====")
        print(f"[EMAIL LOG] API KEY PRESENT: {bool(resend_key)}")
        print(f"[EMAIL LOG] TO: {to}")
        print(f"[EMAIL LOG] SUBJECT: {subject}")
        print(f"[EMAIL LOG] FROM: {settings.EMAIL_FROM_ADDRESS}")

        if not resend_key:
            raise Exception("RESEND_API_KEY is missing")
        if not to:
            raise Exception("Recipient email is missing")

        params = {
            "from":    settings.EMAIL_FROM_ADDRESS,
            "to":      [to],
            "subject": subject,
            "html":    html,
        }

        response = resend.Emails.send(params)
        print(f"[EMAIL LOG] RESPONSE: {response}")
        print("[EMAIL LOG] ✅ EMAIL SENT SUCCESSFULLY\n")
        return {
            "success":  True,
            "email_id": response.get("id") if isinstance(response, dict) else None,
        }

    except Exception as e:
        print(f"\n[EMAIL LOG] ❌ ERROR: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return {"success": False, "error": str(e)}


# ── Notification email ────────────────────────────────────────────────────────

def _build_notification_html(
    title: str,
    message: str,
    institution_name: str,
    institution_address: str,
    institution_logo: str | None,      # already a full URL or None
    chat_url: str,
    file_download_url: str | None = None,
    file_fallback_url: str | None = None,
) -> str:
    """
    Build the notification email HTML.
    1. Logo / institution name header
    2. Notification title + rich-text message
    3. File download button (if file_download_url is provided)
    4. "Open portal" CTA
    5. Footer
    """

    # ── Logo block ─────────────────────────────────────────────────────────────
    if institution_logo:
        # institution_logo is already a fully-qualified URL passed from the CRUD layer
        logo_html = f"""
        <tr>
          <td align="center" style="padding: 28px 0 18px;">
            <img src="{institution_logo}"
                 alt="{institution_name}"
                 style="max-height: 64px; max-width: 220px; object-fit: contain;
                        display: block;"
            />
          </td>
        </tr>"""
    else:
        logo_html = f"""
        <tr>
          <td align="center" style="padding: 28px 0 18px;">
            <div style="
              display: inline-block;
              background: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%);
              color: #ffffff;
              font-size: 19px;
              font-weight: 800;
              letter-spacing: -0.3px;
              padding: 11px 22px;
              border-radius: 12px;
            ">{institution_name}</div>
          </td>
        </tr>"""

    # ── Message body ───────────────────────────────────────────────────────────
    if "<" in message and ">" in message:
        message_body = message
    else:
        message_body = "".join(
            f"<p style='margin:0 0 12px 0;'>{line}</p>"
            for line in message.splitlines()
            if line.strip()
        ) or f"<p style='margin:0;'>{message}</p>"

    # ── File download button (only when a signed URL is available) ─────────────
    file_section_html = ""
    if file_download_url:
        fallback_html = ""
        if file_fallback_url:
            fallback_html = f"""
              <br/>
              <a href="{file_fallback_url}"
                style="font-size:11px;color:#64748b;text-decoration:underline;">
                Link expired? View on portal
              </a>"""
        file_section_html = f"""
          <tr>
            <td style="padding: 0 40px 24px;">
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="
                    background: #f0f9ff;
                    border: 1px solid #bae6fd;
                    border-radius: 12px;
                    padding: 14px 18px;
                  ">
                    <table cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td style="vertical-align: middle;">
                          <span style="font-size: 20px; margin-right: 8px;">📎</span>
                          <span style="font-size: 13px; font-weight: 600; color: #0369a1;">
                            Attachment included
                          </span>
                          <p style="margin: 4px 0 0; font-size: 12px; color: #64748b;">
                            {'Direct link · expires in 7 days.' if file_fallback_url else 'Permanent download link.'}
                          </p>
                        </td>
                        <td align="right" style="vertical-align: middle; white-space: nowrap; padding-left: 16px;">
                          <a href="{file_download_url}"
                            style="
                              display: inline-block;
                              background: #0284c7;
                              color: #ffffff;
                              text-decoration: none;
                              font-size: 12px;
                              font-weight: 700;
                              padding: 9px 18px;
                              border-radius: 8px;
                            ">
                            ⬇ Download File
                          </a>
                          {fallback_html}
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
</head>
<body style="margin:0; padding:0; background:#f1f5f9; font-family:'Segoe UI',Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9; padding:32px 0;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="600" cellpadding="0" cellspacing="0"
               style="background:#ffffff; border-radius:16px; overflow:hidden;
                      box-shadow:0 4px 24px rgba(0,0,0,0.08); max-width:600px; width:100%;">

          <!-- 1. Logo / institution name -->
          {logo_html}

          <!-- Divider -->
          <tr>
            <td style="padding:0 32px;">
              <hr style="border:none; border-top:1px solid #e2e8f0; margin:0;"/>
            </td>
          </tr>

          <!-- 2. Title + Message -->
          <tr>
            <td style="padding:32px 40px 24px;">
              <h1 style="margin:0 0 16px 0; font-size:22px; font-weight:800;
                         color:#0f172a; line-height:1.3;">
                {title}
              </h1>
              <div style="font-size:15px; line-height:1.7; color:#475569;">
                {message_body}
              </div>
            </td>
          </tr>

          <!-- 3. File download (conditional) -->
          {file_section_html}

          <!-- 4. Portal CTA -->
          <tr>
            <td align="center" style="padding:8px 40px 36px;">
              <a href="{chat_url}"
                 style="
                   display:inline-block;
                   background:linear-gradient(135deg,#2563eb 0%,#4f46e5 100%);
                   color:#ffffff;
                   text-decoration:none;
                   font-size:14px;
                   font-weight:700;
                   padding:13px 32px;
                   border-radius:10px;
                   letter-spacing:0.3px;
                 ">
                💬 Open Portal
              </a>
              <p style="margin:10px 0 0; font-size:12px; color:#94a3b8;">
                Click to open the school portal.
              </p>
            </td>
          </tr>

          <!-- 5. Footer -->
          <tr>
            <td style="
              background:#f8fafc;
              border-top:1px solid #e2e8f0;
              padding:20px 40px;
              border-radius:0 0 16px 16px;
            ">
              <p style="margin:0 0 4px 0; font-size:13px; font-weight:700; color:#1e293b;">
                {institution_name}
              </p>
              <p style="margin:0; font-size:12px; color:#94a3b8; line-height:1.5;">
                {institution_address}<br/>
                This is an automated notification — please do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>

</body>
</html>"""


def send_notification_email(
    to: str,
    title: str,
    message: str,
    institution_name: str,
    institution_address: str,
    institution_logo: str | None = None,    # full URL or None
    file_download_url: str | None = None,   # signed R2 URL or None
    file_fallback_url: str | None = None,
) -> dict:
    """
    Send a system notification email to a single recipient.
    Called from notification_crud when send_email=True.
    """
    html = _build_notification_html(
        title=title,
        message=message,
        institution_name=institution_name,
        institution_address=institution_address,
        institution_logo=institution_logo,
        chat_url=FRONTEND_URL,
        file_download_url=file_download_url,
        file_fallback_url=file_fallback_url, 
    )
    return send_email(
        to=to,
        subject=f"[{institution_name}] {title}",
        html=html,
    )


# ── Original helpers (unchanged) ──────────────────────────────────────────────

def send_activation_email(to: str, activation_link: str, user_name: str):
    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;">
    <div style="max-width:600px;margin:0 auto;padding:20px;">
      <h2>Welcome to School Portal, {user_name}!</h2>
      <p>Your account has been created. Click below to activate it:</p>
      <p><a href="{activation_link}" style="background:#4CAF50;color:white;padding:12px 24px;
         text-decoration:none;border-radius:4px;display:inline-block;">Activate Account</a></p>
      <p>Or copy: {activation_link}</p>
      <p>This link expires in 24 hours.</p>
    </div></body></html>"""
    return send_email(to=to, subject="Activate Your School Portal Account", html=html)


def send_password_reset_email(to: str, reset_link: str, user_name: str):
    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;">
    <div style="max-width:600px;margin:0 auto;padding:20px;">
      <h2>Password Reset Request</h2>
      <p>Hi {user_name}, click below to reset your password:</p>
      <p><a href="{reset_link}" style="background:#2196F3;color:white;padding:12px 24px;
         text-decoration:none;border-radius:4px;display:inline-block;">Reset Password</a></p>
      <p>Link expires in 1 hour.</p>
    </div></body></html>"""
    return send_email(to=to, subject="Reset Your Password - Edu Portal", html=html)



def send_otp_email(to: str, otp_code: str, user_name: str):
    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;">
    <div style="max-width:600px;margin:0 auto;padding:20px;">
      <h2>Your Verification Code</h2>
      <p>Hi {user_name}, use this code to complete your login:</p>
      <div style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#2196F3;
                  text-align:center;padding:20px;background:#f5f5f5;border-radius:8px;">
        {otp_code}
      </div>
      <p>Expires in 10 minutes. Never share this code.</p>
    </div></body></html>"""
    return send_email(to=to, subject=f"Your verification code: {otp_code}", html=html)






def send_welcome_email_for_owner(to: str, institute_name: str):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Welcome to YOUR_APP Edu</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:48px 16px;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

      <!-- LOGO LOCKUP: icon + wordmark, centered -->
      <tr>
        <td align="center" style="padding-bottom:32px;">
          <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
            <tr>
              <td valign="middle" style="padding-right:9px;">
                <img src="https://edu.YOUR_APP.com/logo.png" alt=""
                     width="30" height="30"
                     style="display:block;width:30px;height:30px;border-radius:7px;"/>
              </td>
              <td valign="middle">
                <span style="font-size:17px;font-weight:700;color:#0f172a;
                             letter-spacing:-0.3px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;
                             white-space:nowrap;">YOUR_APP Edu</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- CARD -->
      <tr>
        <td style="background:#ffffff;border-radius:12px;
                   box-shadow:0 1px 4px rgba(0,0,0,0.06),0 4px 24px rgba(0,0,0,0.04);">

          <!-- TOP ACCENT -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="height:3px;background:#2563eb;border-radius:12px 12px 0 0;
                         font-size:0;line-height:0;">&nbsp;</td>
            </tr>
          </table>

          <!-- HERO -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:44px 48px 36px;">
                <p style="margin:0 0 8px;font-size:11px;font-weight:600;
                           color:#2563eb;letter-spacing:0.08em;text-transform:uppercase;">
                  Registration received
                </p>
                <h1 style="margin:0 0 16px;font-size:24px;font-weight:700;
                            color:#0f172a;line-height:1.3;
                            font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
                  Welcome to YOUR_APP Edu
                </h1>
                <p style="margin:0;font-size:15px;color:#475569;line-height:1.7;">
                  <strong style="color:#0f172a;">{institute_name}</strong> has been
                  registered. Your account is under review — we'll email you once
                  it's active, usually within 12–48 hours.
                </p>
              </td>
            </tr>
          </table>

          <!-- DIVIDER -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px;">
                <div style="height:1px;background:#f1f5f9;"></div>
              </td>
            </tr>
          </table>

          <!-- STEPS -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:32px 48px 40px;">
                <p style="margin:0 0 24px;font-size:13px;font-weight:600;
                           color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase;">
                  What happens next
                </p>

                <!-- Step 1 -->
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
                  <tr>
                    <td width="36" valign="top" style="padding-top:1px;">
                      <div style="width:24px;height:24px;background:#eff6ff;
                                  border-radius:6px;text-align:center;line-height:24px;
                                  font-size:11px;font-weight:700;color:#2563eb;">1</div>
                    </td>
                    <td>
                      <p style="margin:0 0 3px;font-size:14px;font-weight:600;color:#0f172a;">
                        We review your details
                      </p>
                      <p style="margin:0;font-size:13px;color:#64748b;line-height:1.65;">
                        Our team verifies your institution — this takes 12 to 48 hours.
                      </p>
                    </td>
                  </tr>
                </table>

                <!-- Step 2 -->
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
                  <tr>
                    <td width="36" valign="top" style="padding-top:1px;">
                      <div style="width:24px;height:24px;background:#eff6ff;
                                  border-radius:6px;text-align:center;line-height:24px;
                                  font-size:11px;font-weight:700;color:#2563eb;">2</div>
                    </td>
                    <td>
                      <p style="margin:0 0 3px;font-size:14px;font-weight:600;color:#0f172a;">
                        You get an activation email
                      </p>
                      <p style="margin:0;font-size:13px;color:#64748b;line-height:1.65;">
                        Once approved, we'll send your activation link and dashboard access.
                      </p>
                    </td>
                  </tr>
                </table>

                <!-- Step 3 -->
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td width="36" valign="top" style="padding-top:1px;">
                      <div style="width:24px;height:24px;background:#eff6ff;
                                  border-radius:6px;text-align:center;line-height:24px;
                                  font-size:11px;font-weight:700;color:#2563eb;">3</div>
                    </td>
                    <td>
                      <p style="margin:0 0 3px;font-size:14px;font-weight:600;color:#0f172a;">
                        Your 30-day free trial begins
                      </p>
                      <p style="margin:0;font-size:13px;color:#64748b;line-height:1.65;">
                        Full access to every feature — no card required. Trial starts
                        on activation day, not today.
                      </p>
                    </td>
                  </tr>
                </table>

              </td>
            </tr>
          </table>

          <!-- DIVIDER -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px;">
                <div style="height:1px;background:#f1f5f9;"></div>
              </td>
            </tr>
          </table>

          <!-- AI CHAT NUDGE -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px 32px;" align="center">
                <table cellpadding="0" cellspacing="0"
                  style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;width:100%;">
                  <tr>
                    <td style="padding:18px 24px;">
                      <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td valign="middle">
                            <p style="margin:0 0 2px;font-size:13px;font-weight:600;color:#0f172a;">
                              Have a question while you wait?
                            </p>
                            <p style="margin:0;font-size:12px;color:#64748b;">
                              Our AI support is available 24/7 — no waiting.
                            </p>
                          </td>
                          <td valign="middle" style="padding-left:16px;white-space:nowrap;">
                            <a href="https://edu.YOUR_APP.com/chat"
                               style="display:inline-block;padding:9px 18px;
                                      background:#ffffff;color:#2563eb;font-size:13px;
                                      font-weight:600;text-decoration:none;border-radius:7px;
                                      border:1.5px solid #2563eb;white-space:nowrap;
                                      font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
                              Chat now &rarr;
                            </a>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>

          <!-- SIGN OFF -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px 40px;">
                <p style="margin:0 0 4px;font-size:14px;color:#0f172a;line-height:1.7;">
                  The YOUR_APP Edu Team
                </p>
                <p style="margin:0;font-size:13px;color:#94a3b8;">
                  Questions? Write to
                  <a href="mailto:support@YOUR_APP.com"
                     style="color:#2563eb;text-decoration:none;">support@YOUR_APP.com</a>
                </p>
              </td>
            </tr>
          </table>

        </td>
      </tr>

      <!-- FOOTER -->
      <tr>
        <td align="center" style="padding:28px 0 8px;">
          <p style="margin:0 0 8px;font-size:12px;color:#94a3b8;">
            <a href="https://edu.YOUR_APP.com"
               style="color:#94a3b8;text-decoration:none;">YOUR_APP Edu</a>
            &nbsp;&middot;&nbsp;
            <a href="https://edu.YOUR_APP.com/privacy-policy"
               style="color:#94a3b8;text-decoration:none;">Privacy</a>
            &nbsp;&middot;&nbsp;
            <a href="https://edu.YOUR_APP.com/terms-of-service"
               style="color:#94a3b8;text-decoration:none;">Terms</a>
          </p>
          <p style="margin:0;font-size:11px;color:#cbd5e1;line-height:1.6;">
            You received this because {institute_name} was registered on YOUR_APP Edu.<br/>
            Not you? Email support@YOUR_APP.com immediately.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    return send_email(
        to=to,
        subject=f"Registration received — {institute_name}",
        html=html
    )


def send_activation_email_for_owner(
    to: str,
    institute_name: str,
    login_url: str = "https://app.edu.YOUR_APP.com/login"
):
    features = [
        ("Students &amp; staff", "Add students, teachers, and staff to your institution."),
        ("Classes &amp; sessions", "Set up classes, subjects, and academic sessions."),
        ("Admissions", "Manage admissions workflows and student records."),
        ("Attendance &amp; exams", "Track attendance and schedule examinations."),
        ("Fees", "Collect fees and generate receipts automatically."),
        ("AI chatbot", "Available 24/7 for your students, teachers, and staff."),
    ]

    feature_rows = "".join([f"""
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #f8fafc;">
                    <table cellpadding="0" cellspacing="0">
                      <tr>
                        <td width="28" valign="top" style="padding-top:2px;">
                          <div style="width:18px;height:18px;background:#dcfce7;
                                      border-radius:4px;text-align:center;line-height:18px;
                                      font-size:10px;color:#16a34a;">&#10003;</div>
                        </td>
                        <td>
                          <span style="font-size:13px;font-weight:600;color:#0f172a;">{name}</span>
                          <span style="font-size:13px;color:#64748b;"> — {desc}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>""" for name, desc in features])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Your YOUR_APP Edu account is active</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:48px 16px;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

      <!-- LOGO LOCKUP: icon + wordmark, centered -->
      <tr>
        <td align="center" style="padding-bottom:32px;">
          <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
            <tr>
              <td valign="middle" style="padding-right:9px;">
                <img src="https://edu.YOUR_APP.com/logo.png" alt=""
                     width="30" height="30"
                     style="display:block;width:30px;height:30px;border-radius:7px;"/>
              </td>
              <td valign="middle">
                <span style="font-size:17px;font-weight:700;color:#0f172a;
                             letter-spacing:-0.3px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;
                             white-space:nowrap;">YOUR_APP Edu</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- CARD -->
      <tr>
        <td style="background:#ffffff;border-radius:12px;
                   box-shadow:0 1px 4px rgba(0,0,0,0.06),0 4px 24px rgba(0,0,0,0.04);">

          <!-- TOP ACCENT — green signals activation -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="height:3px;background:#16a34a;border-radius:12px 12px 0 0;
                         font-size:0;line-height:0;">&nbsp;</td>
            </tr>
          </table>

          <!-- HERO -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:44px 48px 36px;">
                <p style="margin:0 0 8px;font-size:11px;font-weight:600;
                           color:#16a34a;letter-spacing:0.08em;text-transform:uppercase;">
                  Account activated
                </p>
                <h1 style="margin:0 0 16px;font-size:24px;font-weight:700;
                            color:#0f172a;line-height:1.3;
                            font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
                  You're live on YOUR_APP Edu
                </h1>
                <p style="margin:0 0 28px;font-size:15px;color:#475569;line-height:1.7;">
                  <strong style="color:#0f172a;">{institute_name}</strong> is now
                  active. Your 30-day free trial starts today — log in and set
                  up your institution.
                </p>
                <a href="{login_url}"
                   style="display:inline-block;padding:13px 32px;
                          background:#1d4ed8;color:#ffffff;font-size:14px;
                          font-weight:600;text-decoration:none;border-radius:8px;
                          font-family:'Segoe UI',Helvetica,Arial,sans-serif;
                          letter-spacing:0.01em;">
                  Open your dashboard &rarr;
                </a>
              </td>
            </tr>
          </table>

          <!-- DIVIDER -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px;">
                <div style="height:1px;background:#f1f5f9;"></div>
              </td>
            </tr>
          </table>

          <!-- FEATURE LIST -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:32px 48px 8px;">
                <p style="margin:0 0 4px;font-size:13px;font-weight:600;
                           color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase;">
                  Everything included
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 48px 32px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  {feature_rows}
                </table>
              </td>
            </tr>
          </table>

          <!-- DIVIDER -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px;">
                <div style="height:1px;background:#f1f5f9;"></div>
              </td>
            </tr>
          </table>

          <!-- AI CHAT NUDGE -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px 32px;">
                <table cellpadding="0" cellspacing="0"
                  style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;width:100%;">
                  <tr>
                    <td style="padding:18px 24px;">
                      <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td valign="middle">
                            <p style="margin:0 0 2px;font-size:13px;font-weight:600;color:#0f172a;">
                              Need help getting started?
                            </p>
                            <p style="margin:0;font-size:12px;color:#64748b;">
                              Our AI support is available 24/7 — instant answers, no waiting.
                            </p>
                          </td>
                          <td valign="middle" style="padding-left:16px;white-space:nowrap;">
                            <a href="https://edu.YOUR_APP.com/chat"
                               style="display:inline-block;padding:9px 18px;
                                      background:#ffffff;color:#2563eb;font-size:13px;
                                      font-weight:600;text-decoration:none;border-radius:7px;
                                      border:1.5px solid #2563eb;white-space:nowrap;
                                      font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
                              Chat now &rarr;
                            </a>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>

          <!-- SIGN OFF -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 48px 40px;">
                <p style="margin:0 0 4px;font-size:14px;color:#0f172a;line-height:1.7;">
                  The YOUR_APP Edu Team
                </p>
                <p style="margin:0;font-size:13px;color:#94a3b8;">
                  Need help?
                  <a href="mailto:support@YOUR_APP.com"
                     style="color:#2563eb;text-decoration:none;">support@YOUR_APP.com</a>
                </p>
              </td>
            </tr>
          </table>

        </td>
      </tr>

      <!-- FOOTER -->
      <tr>
        <td align="center" style="padding:28px 0 8px;">
          <p style="margin:0 0 8px;font-size:12px;color:#94a3b8;">
            <a href="https://edu.YOUR_APP.com"
               style="color:#94a3b8;text-decoration:none;">YOUR_APP Edu</a>
            &nbsp;&middot;&nbsp;
            <a href="https://edu.YOUR_APP.com/privacy-policy"
               style="color:#94a3b8;text-decoration:none;">Privacy</a>
            &nbsp;&middot;&nbsp;
            <a href="https://edu.YOUR_APP.com/terms-of-service"
               style="color:#94a3b8;text-decoration:none;">Terms</a>
          </p>
          <p style="margin:0;font-size:11px;color:#cbd5e1;line-height:1.6;">
            You received this because {institute_name} was registered on YOUR_APP Edu.<br/>
            Not you? Email support@YOUR_APP.com immediately.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    return send_email(
        to=to,
        subject=f"Your account is active — {institute_name}",
        html=html
    )