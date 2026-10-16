# save as /tmp/opencode/webhook_probe.py and run with ../env/bin/python
import hashlib, hmac, json, urllib.request, urllib.error

SECRET = "3f7f8e9875c844cda738d1c80dfcfe5247d11a641644a1a037238abe43ce6ff3"          # same value as RAZORPAY_WEBHOOK_SECRET
ORDER_ID = "order_TEST123"          # a real PENDING payment's provider_order_id, or any string

body = json.dumps({
    "event": "payment.captured",
    "payload": {"payment": {"entity": {"id": "pay_TEST123", "order_id": ORDER_ID}}},
}, separators=(",", ":")).encode()

sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/payments/webhook/",
    data=body,
    headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    method="POST",
)
try:
    print("ACCEPTED:", urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    print("REJECTED:", e.code, e.read().decode())
