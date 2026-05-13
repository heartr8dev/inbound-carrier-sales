# FMCSA QCMobile API — `/qc/services/carriers/docket-number/{mc}` response schema

This document pins the exact field names returned by the FMCSA QCMobile public API for the
docket-number lookup endpoint that powers `POST /api/v1/carrier/verify`.

## Endpoint

```
GET https://mobile.fmcsa.dot.gov/qc/services/carriers/docket-number/{MC}?webKey={WEBKEY}
```

- `{MC}` is the bare numeric docket number (no `MC` prefix). Example: `123456`.
- `{WEBKEY}` is the FMCSA-issued developer webkey (config: `FMCSA_WEBKEY`).
- Response is `application/json` for both success and known-error cases.
- A small HTML page with `<title>FMCSA System Maintenance Page</title>` is returned (HTTP 200)
  during scheduled maintenance — treat as transient failure.

### Probe note

The live probe required by the implementation plan was attempted from this machine and the
FMCSA edge (AWS ALB + WAF) returned HTTP 403 for every request — `curl`, `httpx`, `urllib`,
`WebFetch`, and the various User-Agent variants were all blocked at the WAF layer (likely
egress-IP-based blocking on this WSL2 host; the 403 body is the standard nginx-style
forbidden page, not a JSON error). Because the plan explicitly anticipated this ("the
plan-time webfetch was 403'd by WAF"), the schema below is pinned from the canonical
production response fixtures in the documented Go client
[`brandenc40/qcmobile`](https://github.com/brandenc40/qcmobile) — specifically from
`client_test.go`, which contains verbatim copies of real `/carriers/docket-number` and
`/carriers/{dotNumber}` responses captured from the live FMCSA endpoint. The Go struct
definitions in `carrier.go`, `authority.go`, and `response.go` provide the field-name and
type contract.

## Response envelope (docket-number endpoint)

The response is a JSON object with two top-level keys:

```jsonc
{
  "content": [ <CarrierDetails>, ... ],   // ALWAYS a JSON array for docket-number queries
                                          //  - 0 elements: MC not found
                                          //  - 1+ elements: matching carrier(s)
                                          // (a single MC can in rare cases map to multiple
                                          // DOT numbers; we take the first element.)
  "retrievalDate": "2021-02-28T07:25:05.638+0000"
}
```

When the `webKey` is invalid the API instead returns a 404 with a string-typed `content`:

```json
{
  "content": "Webkey not found",
  "retrievalDate": "...",
  "_links": { "self": {"href": "https://mobile.fmcsa.dot.gov/qc"} }
}
```

The service module must therefore inspect `type(payload["content"])` before indexing.

## `CarrierDetails` shape

```jsonc
{
  "carrier": <Carrier>,
  "_links": { "self": { "href": "..." }, "basics": {...}, ... }   // ignored
}
```

## `Carrier` fields (pinned)

All carrier fields are JSON strings unless otherwise noted. Booleans-as-strings use `"Y"` /
`"N"` / `"u"` (unknown). Dates are ISO `YYYY-MM-DD` or `null`. Monetary amounts are
strings denominated in **thousands of USD** (e.g. `"1000"` = $1,000,000 of BIPD insurance).

| JSON field                          | Type            | Notes                                                                                      |
|-------------------------------------|-----------------|--------------------------------------------------------------------------------------------|
| `allowedToOperate`                  | string          | `"Y"` (allowed) or `"N"` (not allowed). Primary go/no-go gate.                             |
| `statusCode`                        | string          | `"A"` = Active, `"I"` = Inactive. (FMCSA legacy codes — not the literal word `"INACTIVE"`) |
| `legalName`                         | string          | Required. e.g. `"VERIHA TRUCKING INC"`.                                                    |
| `dbaName`                           | string \| null  | Doing-business-as.                                                                         |
| `dotNumber`                         | integer         | USDOT number.                                                                              |
| `safetyRating`                      | string \| null  | `"S"` = Satisfactory, `"C"` = Conditional, `"U"` = Unsatisfactory, `null` = unrated.       |
| `safetyRatingDate`                  | string \| null  | ISO date.                                                                                  |
| `oosDate`                           | string \| null  | Out-of-service date. ISO date. `null` if never OOS or no current OOS order.                |
| `bipdInsuranceOnFile`               | string          | Amount in thousands of USD. `"0"` if none.                                                 |
| `bipdInsuranceRequired`             | string          | `"Y"`/`"N"`.                                                                               |
| `bipdRequiredAmount`                | string          | Amount in thousands of USD.                                                                |
| `cargoInsuranceOnFile`              | string          | Amount in thousands of USD.                                                                |
| `cargoInsuranceRequired`            | string          | `"Y"` / `"N"` / `"u"`.                                                                     |
| `bondInsuranceOnFile`               | string          | Amount in thousands.                                                                       |
| `commonAuthorityStatus`             | string          | `"A"`, `"I"`, `"N"` (none).                                                                |
| `contractAuthorityStatus`           | string          | Same domain.                                                                               |
| `brokerAuthorityStatus`             | string          | Same domain.                                                                               |
| `carrierOperation`                  | object          | `{ "carrierOperationCode": "A", "carrierOperationDesc": "Interstate" }`.                   |
| `censusTypeId`                      | object          | `{ "censusType": "C", "censusTypeDesc": "CARRIER", "censusTypeId": 1 }`.                   |
| `crashTotal`                        | integer         | All crashes.                                                                               |
| `fatalCrash`, `injCrash`, `towawayCrash` | integer    | Crash sub-counts.                                                                          |
| `driverInsp`, `vehicleInsp`, `hazmatInsp` | integer   | Inspection counts.                                                                         |
| `driverOosInsp`, `vehicleOosInsp`, `hazmatOosInsp` | integer | OOS inspection counts.                                                                |
| `driverOosRate`, `vehicleOosRate`, `hazmatOosRate` | number | Percent.                                                                                 |
| `*OosRateNationalAverage`           | string          | Percent as string, e.g. `"5.51"`.                                                          |
| `oosRateNationalAverageYear`        | string          | e.g. `"2009-2010"`.                                                                        |
| `isPassengerCarrier`                | string \| null  | `"Y"` / `"N"`.                                                                             |
| `issScore`                          | unknown \| null | FMCSA Inspection Selection System score; type unspecified in upstream client.              |
| `legalName`, `phyCity`, `phyState`, `phyStreet`, `phyZipcode`, `phyCountry` | string | Physical address.                                                |
| `reviewDate`, `reviewType`          | string / string | Compliance-review metadata.                                                                |
| `safetyReviewDate`, `safetyReviewType` | string       | Safety review metadata.                                                                    |
| `snapshotDate`                      | string \| null  |                                                                                            |
| `totalDrivers`, `totalPowerUnits`   | integer         |                                                                                            |
| `mcs150Outdated`                    | string          | `"Y"` / `"N"`.                                                                             |
| `ein`                               | integer         | Employer ID number.                                                                        |

### Example success payload

Real fixture (from `brandenc40/qcmobile/client_test.go`, captured 2021-02-28; same shape today):

```json
{
  "content": [
    {
      "_links": {
        "basics": {"href": "https://mobile.fmcsa.dot.gov/qc/services/carriers/158121/basics"},
        "carrier active-For-hire authority": {"href": "https://mobile.fmcsa.dot.gov/qc/services/carriers/158121/authority"}
      },
      "carrier": {
        "allowedToOperate": "Y",
        "bipdInsuranceOnFile": "1000",
        "bipdInsuranceRequired": "Y",
        "bipdRequiredAmount": "750",
        "cargoInsuranceOnFile": "0",
        "cargoInsuranceRequired": "u",
        "carrierOperation": {"carrierOperationCode": "A", "carrierOperationDesc": "Interstate"},
        "commonAuthorityStatus": "A",
        "contractAuthorityStatus": "A",
        "brokerAuthorityStatus": "N",
        "dbaName": null,
        "dotNumber": 158121,
        "legalName": "VERIHA TRUCKING INC",
        "oosDate": null,
        "safetyRating": "S",
        "safetyRatingDate": "1996-04-25",
        "statusCode": "A"
      }
    }
  ],
  "retrievalDate": "2021-02-28T07:25:05.638+0000"
}
```

### Example "not found" payload

Empty content list:

```json
{
  "content": [],
  "retrievalDate": "2026-05-13T02:00:00.000+0000"
}
```

The service treats this as `mc_not_found` and returns `is_eligible=false`.

### Example webkey-error payload (HTTP 404)

```json
{
  "content": "Webkey not found",
  "retrievalDate": "...",
  "_links": {"self": {"href": "https://mobile.fmcsa.dot.gov/qc"}}
}
```

The service must detect `isinstance(payload.get("content"), str)` and raise a clear
configuration error (treated as 503 to the caller).

### Maintenance page

A 200 response body containing `<title>FMCSA System Maintenance Page</title>` indicates
scheduled maintenance. The client treats this identically to an upstream 5xx (circuit
breaker counts it as a failure; HTTP response to caller is 503).

## Mapping to our `CarrierVerification` model

| `CarrierVerification` column | Source                                                                |
|------------------------------|-----------------------------------------------------------------------|
| `mc_number`                  | Request input (zero-padded? no — stored as the raw digits)            |
| `legal_name`                 | `carrier.legalName`                                                   |
| `dba_name`                   | `carrier.dbaName`                                                     |
| `operating_status`           | `carrier.carrierOperation.carrierOperationDesc` (`"Interstate"`, etc.) — _unless_ `allowedToOperate == "N"`, in which case we synthesize `"NOT AUTHORIZED"` for downstream readability. |
| `authority_type`             | Derived: `"common"` if `commonAuthorityStatus == "A"`, else `"contract"` if `contractAuthorityStatus == "A"`, else `"broker"` if `brokerAuthorityStatus == "A"`, else `"none"`. |
| `allowed_to_operate`         | `carrier.allowedToOperate == "Y"`                                     |
| `safety_rating`              | Mapped: `"S"` → `"Satisfactory"`, `"C"` → `"Conditional"`, `"U"` → `"Unsatisfactory"`, `null` → `None`. |
| `insurance_bipd_on_file`     | `Decimal(carrier.bipdInsuranceOnFile) * 1000` (FMCSA reports in thousands). |
| `insurance_cargo_on_file`    | `Decimal(carrier.cargoInsuranceOnFile) * 1000`                        |
| `is_eligible`                | Output of `evaluate_eligibility(...)`                                 |
| `rejection_reason`           | Output of `evaluate_eligibility(...)`                                 |
| `raw_response`               | The entire JSON payload (the wrapper, not just the carrier object)    |
| `verified_at`                | `func.now()` server-side                                              |

## Eligibility rules (pinned to discovered field names)

1. Reject (`not_allowed_to_operate`) if `carrier.allowedToOperate != "Y"`.
2. Reject (`inactive`) if `carrier.statusCode == "I"` (FMCSA inactive code) **or** the
   synthesized `operating_status` contains `"NOT AUTHORIZED"`.
3. Reject (`out_of_service`) if `carrier.oosDate` is set and parses to a date `<= today`.
4. Reject (`unsatisfactory_safety_rating`) if `carrier.safetyRating == "U"`.
5. Warn-and-pass (`is_eligible=True`, `rejection_reason="conditional_safety_rating"`) if
   `carrier.safetyRating == "C"`.
6. Otherwise pass.
