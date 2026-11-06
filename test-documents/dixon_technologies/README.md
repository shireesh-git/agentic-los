# Test data: Dixon Technologies (India) Limited (new-to-bank prospect)

Used to test the new-prospect journey: the data-acquisition agents fetch what the connected APIs provide, and the RM uploads the rest.

```
python test-documents/dixon_technologies/prepare.py      # downloads ./public (once), generates ./demo
```

## Real public data

| Item | Value | Source |
|---|---|---|
| CIN | L32101UP1993PLC066581 | Annual report FY2025-26; GLEIF (`registeredAs`) |
| LEI | 335800D7XO7AVXXJ8575 | GLEIF API (fetched live by the Identity agent) |
| PAN / GSTIN | AAACD3641D / 09AAACD3641D1Z2 | Public GST registration search |
| Registered office | B-14 & 15, Phase-II, Noida 201305 | Annual report |
| Directors and DINs | Sunil Vachani (00025431), Atul B. Lall (00781436) and others | Annual report FY2025-26 (DINs where stated there) |
| Standalone audited statements, FY2024–FY2026 | Revenue ₹6,411 / 5,401 / 3,930 Cr; PAT ₹186 / 566 / 759 Cr | `public/annual_report_fy2025.pdf`, `public/annual_report_fy2026.pdf` (BSE) |
| Rating | [ICRA]AA (Stable) / [ICRA]A1+; ₹2,625 Cr bank lines rated | `public/icra_rationale_2026-01-06.pdf` (ICRA) |
| Key bankers, security | ICICI, HDFC, Citi, SBI, SMBC, JP Morgan; working-capital limits secured by hypothecation of stock and receivables | Annual report |

Public documents:

- Annual Report 2025-26: <https://www.bseindia.com/xml-data/corpfiling/AttachHis/5ef88e3c-352d-4223-a8ec-bdd7d3aa31c1.pdf>
- Annual Report 2024-25: <https://www.bseindia.com/xml-data/corpfiling/AttachHis/7eabc370-b827-435c-9dd2-8a70553a8062.pdf>
- ICRA rationale, 6 January 2026: <https://www.icra.in/Rating/GetRationalReportFilePdf?id=140153>

The public PDFs are not committed: they are about 15 MB each, and `prepare.py` downloads each one once.

## Demo data (generated, marked "UAT DEMO DATA" on every page)

A bank obtains these documents from sources that are not public. They are generated to agree with the public figures:

- **MCA master data printout:** identifiers, capital and directors are taken from the annual report. The charge entry is illustrative.
- **KYC pack:** PAN, CIN and GSTIN are real. The promoter holding (28.5%) is from the shareholding pattern. Signatory verification is demo data.
- **Commercial bureau report (CMR format):**
  - The lender totals match the limits ICRA rated: fund-based ₹535 Cr, non-fund-based ₹1,880 Cr.
  - Fund-based outstanding is nil, matching the balance sheet: the ₹172 Cr of borrowings there are loans from subsidiaries.
  - The split by lender is illustrative.
- **Bank statement, April–September 2026:** credits match H1 FY2027 sales (₹1,080 Cr and ₹1,593 Cr in the two quarters), including GST.
- **GST returns, FY2025-26:** taxable value is ₹3,862 Cr against reported revenue of ₹3,930 Cr. The difference is PLI incentives and other operating income, which are not GST supplies.

## What the verification agent should find

- **Pass:**
  - CIN and PAN match across all sources;
  - all three years reconcile, and FY2025 is identical in both annual reports;
  - GST turnover is within 2% of revenue;
  - bureau conduct is clean;
  - sanctions screening is clear.
- **For review:**
  - FY2026 other income (₹802 Cr, including a ₹690 Cr gain on equity investments) is 90% of profit before tax;
  - balance-sheet borrowings are not in the bureau report, because they are inter-company loans;
  - bank credits run ahead of FY2026 revenue, reflecting growth in H1 FY2027.
