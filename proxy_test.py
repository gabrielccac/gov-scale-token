import requests

proxies = {
    'http': 'http://customer-govscale_tQf5K-cc-BR:Govpassword123=@pr.oxylabs.io:7777',
    'https': 'http://customer-govscale_tQf5K-cc-BR:Govpassword123=@pr.oxylabs.io:7777'
}

authToken = 'eyJhbGciOiJSUzUxMiJ9.eyJzdWIiOiIwOTUxMjk4OTkyMSIsInRpcG8iOiJGIiwiaWRlbnRpZmljYWNhb19mb3JuZWNlZG9yIjoiNTQ1Nzk1NjMwMDAxMDUiLCJpZF9zZXNzYW8iOjg4Nzk3NjgyLCJvcmlnZW1fc2Vzc2FvIjoiVyIsImF1dGVudGljYWNhbyI6IkwiLCJuaXZlaXNfY29uZmlhYmlsaWRhZGUiOlsxLDNdLCJ0aXBvX2Zvcm5lY2Vkb3IiOiJKIiwicG9ydGVfZm9ybmVjZWRvciI6IjEiLCJpYXQiOjE3NTc1MjU3MzQsImV4cCI6MTc1NzUyNjMzNH0.EvE5Bhgfy3JCnFGa6aarzYw6cGT40Zw7tUCaVk_WLdq1MMEEWdoGcOPXzlwPYwB7drzYK0wUQQPI-8IJkK0rEHK9qcuAcA42mFBlAEHT7EVG_jGldt8-ZPx6hb91xIZqv_o-9TjECpiSRsIiPw1Z3q81dQjPSeCUo3je36_WIRtUdL6Ska5YM8TsvZv_xVem0sZX1eMNIUDBPRubS1Az2RrmncP1mWHyNJjYd3ouSV2s910lhqY3PfX4fMliFiVCpaOT51Ko22OOc8FZUxPPRIToCj-BwSedqblr1Ayz4HdAPmhuzP1o1BiR_5TpyzQPohElDwJbn7M1qDeK66Ovpex-hIubjJnVftSvFRNBNZnneuper6KOSRPu-eJUXGODSzqYl2AzEv53OL4mLesJPyryIxdUcvFj4A9nljC7Uoq-ug_-OCzsK_AgE1yZRj2ZjkwGF9rsVo4qRMHYwDGjF4S_njVTHn-Hq4vwR5-dibEVdw7lcLMS_QxbZKlUoQE3vyVZLSQr7K2CcGS1lDBP_ll41ec1Jh_Y-ADBla_zxEmsqqYGgtOFTN_4KvFoXNK06iCfax5aLBLulDWaH1VX1rvUpX8b29tCB8I9oyxdpOyPDJ3_a1udhl-5u_aepR38rcHOW7-n0Dc8yHkQSo3P6oRKVPhrd1-1sbKshtJdHfc'  # Add your bearer token here

headers = {
    'Authorization': f'Bearer {authToken}'
}

try:
    response = requests.get('https://cnetmobile.estaleiro.serpro.gov.br/comprasnet-usuario/v1/usuario', proxies=proxies, headers=headers)
    print('Response status:', response.status_code)
    print('Response data:', response.text)
except Exception as e:
    print('Request error:', e)

