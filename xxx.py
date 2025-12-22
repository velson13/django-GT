from pprint import pprint

# adjust this import path to match your project
from gtbook.utils.faktura_xml_extract import extract_full_invoice

data = extract_full_invoice("250114.xml", output_pdf="output_invoice.pdf")

print("\n========= EXTRACTED DATA =========\n")
pprint(data)
print("\n========= END =========\n")
