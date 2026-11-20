# WorldLink public launch · customer/router/payment operations

## What changed in this release

- An already-open paid/voucher receipt counts down and changes to **Your internet package has expired / Muda wa kifurushi chako cha intaneti umeisha** with **Buy internet again**. If the same Omada device returns to the portal after its entitlement ends, a clear expiry notice appears above packages. The site remains reachable before authorization so the guest can buy again. iOS cannot be remotely forced to reopen its captive-browser popup just because Omada's session expires; a guest can open their portal URL or an ordinary HTTP site, and may need to toggle Wi-Fi if iOS does not prompt.
- EvPay Test Lab is a **WorldLink superuser-only** tool in the platform navigation. Tenant owners, managers and cashiers cannot open its URLs or initiate tests even by typing the link. Test payments remain isolated from actual hotspot revenue.
- Manual payment-method management and new public manual payment requests have been retired (404). Historical manual requests remain preserved for audit; **cash/bank printed vouchers remain supported** and still need a verified sale before redemption.
- A WorldLink manager can now **approve or revoke an individual business** for automatic EvPay checkout from its router review page. The approval is audited and overrides old `EVPAY_COLLECTION_COMPANY_IDS` entries. This is only one gate; it cannot bypass merchant permission, an active business, an online approved AP, or the one-time global rollout switch.
- WorldLink staff can **Load Omada site list** on the router-review page to choose a site name and Open API `siteId` without running a command. The device Inform `omadacId` is still copied from the site's Omada inform URL; do not assume both IDs always match.

## One-time platform setup — not repeated for each business

1. WorldLink must have the central Omada controller online, DNS/TLS, approved outbound device-management connectivity, and the WorldLink-hosted public portal.
2. WorldLink must have valid, authorized **live** EvPay merchant credentials and written provider agreement covering collections for other businesses. WorldLink is the actual payment recipient; each sale is attributed to one tenant in WorldLink's ledger.
3. On the main Django VPS, the environment switches `EVPAY_ENABLED`, `EVPAY_PUBLIC_CHECKOUT_ENABLED`, `OMADA_LIVE_ENABLED`, and **`EVPAY_MULTITENANT_ENABLED`** must be set to True once by WorldLink operations. Existing Redis, signed webhook and background workers must stay healthy. Do **not** reconfigure credentials for each business.
4. After this release is deployed and migration `payments.0004` is applied, new business approvals use the web console. The old `EVPAY_COLLECTION_COMPANY_IDS=1,2` list is **legacy fallback only** for IDs without an explicit new web decision. Browser revocation overrides it.

## Remote customer onboarding — repeat these browser steps per business

**A. Business owner (their WorldLink account)**

1. Sign up or accept the WorldLink invitation. Enter business contact, location, logo and phone. Create a Wi-Fi package and enable the captive portal.
2. Open **Network → Routers → Add router** and choose **TP-Link Omada**. Enter a friendly router name, physical location, exact model and **serial number** from the EAP's label.
3. Open **Omada setup** on that saved router, choose **WorldLink central Omada**, and enter the **AP MAC** (not the gateway/router MAC), desired guest **SSID** (case-sensitive), and notes like ISP, site contact, whether the AP is currently on another controller. Click **Request WorldLink review**. Never paste router passwords or EvPay keys.
4. The EAP and its local internet router must be powered on and able to reach the central controller. For a far-away owner, a local person may need to log into the EAP/old controller to set the WorldLink **Inform URL** or migrate/adopt the device. WorldLink cannot adopt powered-off devices or bypass local access simply because the owner submitted a serial/MAC. No customer VPN/Tailscale account is normally needed when the device can initiate the required outbound connection.

**B. WorldLink staff (browser only)**

5. Open **WorldLink Control Center → All businesses**. Confirm the business's identity and required subscription/status. Set it **Active** only after verifying their account; do not activate on an unreviewed form alone.
6. Sign in to your **Omada central controller** (the existing TP-Link site, not a new website). Create a **separate site for this business**. Configure its guest SSID, external captive portal URL pointing to the business's WorldLink `https://wifi.worldlinksecurity.co.tz/wifi/<business-slug>/`, and pre-auth access to WorldLink/Omada portal resources. Ensure the site and EAP are correctly separated from other businesses.
7. In Omada's site/device settings, copy its **device Inform `omadacId`** from its Inform URL and share the Inform URL securely with the local owner/installer. Have the local person configure the device's Inform URL or migrate it from an existing Omada controller. Accept/adopt the AP **in this business site**. Verify the actual AP MAC and serial match the submitted request. Never use the WorldLink controller ID from the cloud browser URL in place of a site ID.
8. Go to **WorldLink Control Center → Router onboarding → Open review page**. Click **Load Omada site list** and select the new site; it fills name/Open API site ID. Enter the **device Inform ID** from Omada separately. Approve site mapping. Wait for the existing managed monitor worker; its fresh read-only result must say **Connected**. You can refresh the page without running a CLI command.
9. Physically test a guest phone on this exact AP/SSID. Confirm the **correct business portal** opens without exposing any other business's packages. Then choose **Approve printed voucher activation** for this AP, if the business will sell vouchers.
10. Only with explicit permission under WorldLink's agreement with EvPay, tick the financial attestation and choose **Approve this AP for live payments**. In the new **WorldLink merchant approval** section, confirm permission again and click **Approve business EvPay checkout**. If the one-time global switch is disabled, get WorldLink operations to enable it once first. A merchant approval is per company; each newly added AP needs its own router review and approval.

**C. Final test (without forcing money through the system)**

11. Connect a guest phone to the business SSID. Confirm voucher entry appears only when allowed; **Pay with mobile money** appears only when the company and exact AP are approved and a valid Omada redirect is present.
12. Test a genuinely sold voucher: record cash/bank sale in **Voucher batches**, redeem on the correct guest phone, browse a public site, then wait for its short package to expire. Test the expired screen and **Buy internet again**. A printed voucher is *not* an EvPay deposit or WorldLink withdrawable fund.
13. Once EvPay is reachable and the business has permission, conduct **one small authorized live payment** to a consenting phone. Verify provider-signed webhook or secure server reconciliation confirms SUCCESS/SETTLED, Omada activation appears, guest internet works, and the sale appears under that *business* in Live Wi-Fi payments/Sales reports. An EvPay PENDING or provider HTTP 523 must **never** open internet automatically.
14. Verify other tenant accounts cannot see or approve this business's devices or payments. A test in WorldLink's superuser lab must not appear as actual customer revenue.

## Financial display

EvPay SUCCESS means customer payment is confirmed, not necessarily cleared cash. A WorldLink-controlled merchant settlement and finance verification process must distinguish **received by provider**, **cleared**, and **available to withdraw**. Do not auto-credit the customer's full gross payment to withdrawable balance simply because Wi-Fi was activated. Business owners see legitimate verified payments and vouchers separately; they cannot change shared EvPay API credentials.

## Emergency stop (browser)

- On the specific Router review page, **Revoke payment approval** stops new AP charges; **Stop EvPay checkout for this business** overrides even a legacy `.env` ID and stops new business charges, while retaining historical records. These controls do not automatically revoke a guest's already-authorized time in Omada; emergency customer disconnection is a separate device operation.
- **Revoke voucher access** stops new redemptions on that AP.
- Keep the live system as a staged rollout. Do not advertise compatibility with every TP-Link or MikroTik device: each model needs hardware/firmware and portal integration verification. MikroTik onboarding is a separate connection workflow and not the central Omada AP adoption flow.
