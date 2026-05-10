from fastapi import FastAPI, Request, Response

app = FastAPI(title="Service B - SOAP/XML Mock")


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-b"}


@app.post("/soap")
async def soap_endpoint(request: Request):
    body = await request.body()
    soap_action = request.headers.get("SOAPAction", "unknown")

    # Minimal SOAP response based on action
    if soap_action == "checkStock":
        response_xml = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkStockResponse>
      <available>true</available>
      <quantity>500</quantity>
      <warehouse>Istanbul</warehouse>
    </checkStockResponse>
  </soap:Body>
</soap:Envelope>"""
    else:
        response_xml = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <genericResponse>
      <status>ok</status>
      <action>{action}</action>
    </genericResponse>
  </soap:Body>
</soap:Envelope>""".format(action=soap_action)

    return Response(content=response_xml, media_type="text/xml")
