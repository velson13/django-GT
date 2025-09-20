import requests
import xml.etree.ElementTree as ET
from django.conf import settings

def get_company_accounts(pib: str) -> str:
    url = "https://webservices.nbs.rs/CommunicationOfficeService1_0/CompanyAccountService.asmx"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://communicationoffice.nbs.rs/GetCompanyAccount",
    }

    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Header>
        <AuthenticationHeader xmlns="http://communicationoffice.nbs.rs">
          <UserName>{settings.NBS_USERNAME}</UserName>
          <Password>{settings.NBS_PASSWORD}</Password>
          <LicenceID>{settings.NBS_LICENCE_ID}</LicenceID>
        </AuthenticationHeader>
      </soap:Header>
      <soap:Body>
        <GetCompanyAccount xmlns="http://communicationoffice.nbs.rs">
          <nationalIdentificationNumber>0</nationalIdentificationNumber>
          <taxIdentificationNumber>{pib}</taxIdentificationNumber>
          <bankCode>0</bankCode>
          <accountNumber>0</accountNumber>
          <controlNumber>0</controlNumber>
          <companyName></companyName>
          <city></city>
          <startItemNumber>0</startItemNumber>
          <endItemNumber>0</endItemNumber>
        </GetCompanyAccount>
      </soap:Body>
    </soap:Envelope>"""

    response = requests.post(url, data=soap_body.encode("utf-8"), headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_company_accounts(xml_str: str):
    accounts = []
    root = ET.fromstring(xml_str)

    for account in root.findall(".//CompanyAccount"):
        accounts.append({
            "Account": account.findtext("Account"),
            "BankCode": account.findtext("BankCode"),
            "BankName": account.findtext("BankName"),
            "CompanyName": account.findtext("CompanyName"),
            "TaxIdentificationNumber": account.findtext("TaxIdentificationNumber"),
            "NationalIdentificationNumber": account.findtext("NationalIdentificationNumber"),
            "Address": account.findtext("Address"),
            "City": account.findtext("City"),
            "MunicipalityName": account.findtext("MunicipalityName"),
            "ActivityCode": account.findtext("ActivityCode"),
            "ActivityName": account.findtext("ActivityName"),
            "StatusID": account.findtext("CompanyAccountStatusID"),
            "BlockadeStatusID": account.findtext("CompanyAccountBlockadeStatusID"),
        })
    return accounts

