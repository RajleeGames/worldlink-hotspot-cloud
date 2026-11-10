EN = {
    'tagline': 'Fast, simple guest Wi-Fi', 'choose': 'Choose your Wi-Fi package',
    'packages': 'Available packages', 'minutes': 'minutes', 'hours': 'hours', 'days': 'days',
    'speed': 'Speed', 'devices': 'Devices', 'data': 'Data', 'unlimited': 'No data cap',
    'buy': 'Select package', 'no_packages': 'No packages are available at the moment.',
    'voucher': 'Have a voucher?', 'voucher_note': 'Voucher login will be available after the hotspot router is connected.',
    'help': 'Need help?', 'payment': 'Payment request', 'customer_name': 'Your name',
    'phone': 'Phone number', 'method': 'Payment method', 'continue': 'Create payment request',
    'back': 'Back to packages', 'payment_notice': 'Payments are manually confirmed by this business. This page cannot yet authorize internet access.',
    'pay_to': 'Pay to', 'account': 'Account / till', 'recipient': 'Recipient',
    'reference': 'Your reference', 'status': 'Request status', 'pending': 'Awaiting verification',
    'paid': 'Manually confirmed', 'cancelled': 'Cancelled', 'instructions': 'Payment instructions',
    'no_methods': 'No payment methods are configured yet. Contact the business.',
    'thanks': 'Your request is recorded.', 'not_live': 'Wi-Fi access will only be activated when the router integration is enabled.',
    'refresh': 'Refresh status', 'order': 'Request number', 'package': 'Package', 'price': 'Price',
    'privacy': 'Your phone number is shared with this Wi-Fi business to process your request.',
    'manual': 'Manual verification', 'contact': 'Contact the business', 'secure': 'Powered by WorldLink Hotspot Cloud',
}
SW = {
    'tagline': 'Wi-Fi rahisi na ya haraka', 'choose': 'Chagua kifurushi cha Wi-Fi',
    'packages': 'Vifurushi vinavyopatikana', 'minutes': 'dakika', 'hours': 'saa', 'days': 'siku',
    'speed': 'Kasi', 'devices': 'Vifaa', 'data': 'Data', 'unlimited': 'Hakuna kikomo cha data',
    'buy': 'Chagua kifurushi', 'no_packages': 'Hakuna vifurushi vinavyopatikana kwa sasa.',
    'voucher': 'Una vocha?', 'voucher_note': 'Kuingia kwa vocha kutapatikana baada ya kuunganisha ruta.',
    'help': 'Unahitaji msaada?', 'payment': 'Ombi la malipo', 'customer_name': 'Jina lako',
    'phone': 'Namba ya simu', 'method': 'Njia ya malipo', 'continue': 'Tuma ombi la malipo',
    'back': 'Rudi kwenye vifurushi', 'payment_notice': 'Malipo yanathibitishwa na biashara hii. Ukurasa huu hauwashi intaneti bado.',
    'pay_to': 'Lipa kwa', 'account': 'Akaunti / namba ya biashara', 'recipient': 'Mpokeaji',
    'reference': 'Namba ya kumbukumbu', 'status': 'Hali ya ombi', 'pending': 'Inasubiri kuthibitishwa',
    'paid': 'Imethibitishwa kwa mkono', 'cancelled': 'Imefutwa', 'instructions': 'Maelekezo ya malipo',
    'no_methods': 'Hakuna njia ya malipo iliyowekwa. Wasiliana na biashara.',
    'thanks': 'Ombi lako limepokelewa.', 'not_live': 'Intaneti itawezeshwa baada ya kuunganisha mfumo na ruta.',
    'refresh': 'Angalia hali tena', 'order': 'Namba ya ombi', 'package': 'Kifurushi', 'price': 'Bei',
    'privacy': 'Namba yako itashirikiwa na biashara hii kwa ajili ya kushughulikia ombi.',
    'manual': 'Uthibitisho wa mkono', 'contact': 'Wasiliana na biashara', 'secure': 'Imewezeshwa na WorldLink Hotspot Cloud',
}

def words_for(code):
    return SW if code == 'sw' else EN
