# WorldLink Platform — Monthly subscriptions

**Price:** TZS 20,000 for one calendar month per business. Paid to the WorldLink EvPay merchant account; separate from hotspot customer payments, business revenue and business withdrawals.

## Feature flags (one-time only)

```ini
WORLDLINK_SUBSCRIPTIONS_ENABLED=False
WORLDLINK_SUBSCRIPTIONS_ENFORCED=False
EVPAY_SUBSCRIPTION_WEBHOOK_TOKEN=GENERATE_A_NEW_SECRET_AT_LEAST_30_CHARS
```

The subscription webhook uses the existing `EVPAY_WEBHOOK_SECRET`, `EVPAY_SIG_KEY`, `EVPAY_CLIENT_ID`, `EVPAY_CLIENT_SECRET`, and `EVPAY_PUBLIC_BASE_URL` already configured for live EvPay. Leave all existing payment/Omada settings as they are.

**Stage 1: Controlled live payment test:** set `WORLDLINK_SUBSCRIPTIONS_ENABLED=True` while leaving `WORLDLINK_SUBSCRIPTIONS_ENFORCED=False`. Restart Django. The business owner will see a Pay TZS 20,000 button. Use a dedicated signed callback at `/payments/subscriptions/webhook/<token>/`, not the Wi-Fi payment callback.

**Stage 2: Launch enforcement:** after a confirmed subscription test and a controlled plan for existing businesses, set `WORLDLINK_SUBSCRIPTIONS_ENFORCED=True` and restart Django. Expired businesses are redirected to the subscription page; guest sessions already paid for are not terminated. Each business gets its own expiry date and own subscription history.

### Dashboard
Business owner -> **Subscriptions**. The page displays monthly fee, paid-through date, Pay with Mobile Money, a pending payment status and subscription history. The same paid-through date appears in **Business settings** and the dashboard.

### WorldLink operations
**Platform subscriptions** lists verified payment records for all businesses, separate from Wi-Fi customer collections. There is no manual “mark paid” control. Payment status must come from a signed EvPay callback or authenticated EvPay lookup.

### Recovery
For a pending/unknown request, use `python manage.py reconcile_evpay_subscriptions --limit 25`. This only queries the original reference. Never resend the charge automatically. If the provider returns 523 or is unreachable, leave the attempt unconfirmed and contact EvPay with the reference. A reversed/refunded subscription is flagged for WorldLink review.

### Existing companies
The `Company.subscription_ends` field already exists. Before turning enforcement on, review existing businesses. Any with no paid-through date will be redirected to the subscription page. If a temporary grace period is approved, set its end date using a staff-controlled process; never mark a nonexistent EvPay transaction as paid.

### Monthly policy
This is **manual renewal by the owner each month** with an EvPay USSD prompt; it does not initiate automatic recurring deductions. Payment extending an unexpired subscription starts from the existing end date, avoiding loss of paid days. If a user pays on the 31st, the next date is the final day of the shorter next month.
