# WorldLink — voucher redemption & one-AP business cutover

This phase adds **WorldLink printed-voucher redemption** to an Omada **external portal**. These codes are not Omada's built-in vouchers. A business records a cash/bank sale, then a guest enters the code on the Wi-Fi captive page. The server asks Omada to authorize exactly that client's MAC for the purchased plan duration. No EvPay debit is initiated and the cash sale never credits a WorldLink-held merchant wallet.

## On the current Django VPS

1. Back up your **live** SQLite database with the validated `sqlite3.Connection.backup()` procedure used previously, and back up `.env` privately. Never use a local Windows SQLite file to overwrite the VPS database.
2. Pull the reviewed commit from GitHub, then with the existing venv active run:

   ```bash
   python manage.py check
   python manage.py migrate --plan
   python manage.py migrate
   python manage.py collectstatic --noinput
   sudo systemctl restart worldlink-hotspot.service worldlink-evpay-fast.service worldlink-evpay-omada.service
   sudo systemctl is-active worldlink-hotspot.service worldlink-evpay-fast.service worldlink-evpay-omada.service
   ```

3. Keep central Omada observations fresh (vouchers require a positive observation within 120 seconds):

   ```bash
   sudo cp deploy/worldlink-omada-managed.service.example /etc/systemd/system/worldlink-omada-managed.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now worldlink-omada-managed.service
   sudo systemctl is-active worldlink-omada-managed.service
   python manage.py poll_omada_managed
   ```

## Test one actual EAP225 with the new business

1. **Do not delete Eaglelink or its recorded sales.** Only one physical EAP225 exists, so test the new company's signup, voucher batch, dummy router and staff review *without* live approval first.
2. When ready to transfer, stop new Eaglelink sales, reconcile any pending EvPay orders, and wait until **all** paid and voucher sessions have expired. Back up records.
3. On the Django VPS set `OMADA_PILOT_COMPANY_ID=0` and clear `OMADA_AP_MAC` and `OMADA_SSID` (only for this old legacy pilot; do not disable the shared controller, EvPay provider, or past collections). Restart Django and workers. This deliberately closes the old hotspot pilot's live gate.
4. WorldLink staff open the **old Eaglelink** router review and use **Retire approval · preserve history** after typing `RETIRE`. The server blocks release if recent pending payments or active entitlements remain. The old router, original vouchers and EvPay history remain in Django.
5. In the **central Omada Controller** move/re-adopt the actual physical EAP225 to a site owned by the new business. Configure its real guest SSID and **External Portal** redirect to the new tenant's exact public WorldLink `/wifi/<slug>/` URL. Make the public portal reachable from unauthenticated guest clients (walled garden). The AP must show online in **its new site**.
6. In the new business router request replace the earlier **dummy MAC** with the actual AP MAC and real guest SSID. Submit for staff review again if needed. Staff assign the correct **new-business** Omada inform site ID and Open API site ID; do **not** copy Eaglelink's site credentials or IDs.
7. Run `python manage.py poll_omada_managed` and confirm the new AP reports **Connected**. The staff review page has a distinct **Approve printed voucher activation** checkbox/action. It does not enable EvPay merchant collection. Keep `EVPAY_MULTITENANT_ENABLED=False` until third-party collections are formally permitted by EvPay.
8. In the new business account create a 5-minute TZS100 plan, create one voucher, and **Record sale** against a truly received cash/bank payment. Connect a real phone to the new Wi-Fi. The captive portal shows the **voucher code** input. Type the voucher; confirm successful authorization, internet access and actual expiry. A different phone must not be able to redeem the same code. Dashboard shows voucher sold/redeemed and cash revenue under the **business-held** category; WorldLink wallet must remain unchanged.
9. Test a real EvPay payment for the new business only after documented provider approval, separate staff payment approval, company allowlisting and the multitenant feature gate. Provider `PENDING` is not paid; `SUCCESS`/`SETTLED` is not independently cleared for withdrawal. Never manufacture provider callbacks to unlock Wi-Fi.

The WorldLink hotspot operator remains server-only; do not put operator passwords or controller secrets into tenant forms. Ensure any secrets previously shared in chat or terminal screenshots are rotated before unrestricted public launch.
