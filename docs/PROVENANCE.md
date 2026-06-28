# Data provenance and licensing

Last updated: 27 June 2026

This document records where every dataset in Tender Watch comes from, how it was
obtained, what is done with it, and the open licensing questions that still need to be
confirmed. It is written to be honest about what is settled and what is not.

> Status note: the licensing positions marked "TO CONFIRM" below are not yet verified.
> They should be checked, and ideally reviewed by a qualified Indian lawyer, before any
> public launch. Do not treat this document as a statement that all reuse is cleared.

---

## 1. Source: CPPP procurement data

**What it is.** Records of tenders (notices) and awards (results) from India's Central
Public Procurement Portal, eprocure.gov.in, covering central, state, public sector, and
related procuring bodies.

**Original publisher.** The Government of India, via the CPPP / eprocure.gov.in portal.
This is information that the government publishes openly as part of procurement
transparency.

**How Tender Watch obtained it.** Not directly from the portal. The project uses two
scraped SQLite databases that are a public mirror of the portal, published at
https://tender.sarthaksidhant.com/. These were downloaded once and are treated as a
read only snapshot.

**Snapshot date.** The data is a point in time copy, not a live feed. The snapshot used
by this project is dated 26 June 2026.

**What is done with it.** It is parsed, typed, normalised, and aggregated into the
cleaned tables described in the README. Individual records are reproduced as they appear
in the public source, with a link back to the official portal by Tender ID or Reference
Number.

**Licensing status. TO CONFIRM.** Government of India data is often available under the
Government Open Data License India (GODL) or similar terms, and procurement results are
published for public scrutiny. However, two things are not yet established:

1. The exact licence or terms of use that apply to the CPPP data and whether they permit
   republication and redistribution in this form.
2. The terms under which the third party mirror at tender.sarthaksidhant.com was created
   and may be reused, and whether relying on the mirror (rather than the portal) carries
   any additional condition.

Action: confirm the applicable licence for the source data, and confirm permission or
terms for using the mirror, before publishing.

---

## 2. Source: MCA registered companies

**What it is.** A list of about 1.99 million companies from the Ministry of Corporate
Affairs (MCA) register, with fields including company name, Corporate Identity Number
(CIN), status, incorporation date, paid up capital, state, and an email address.

**Original publisher.** The Ministry of Corporate Affairs, Government of India.

**How Tender Watch obtained it.** Downloaded from the Government of India Open
Government Data (OGD) platform, data.gov.in, from the "Registrars of Companies (ROC)
wise Company Master Data" resource at
https://www.data.gov.in/resource/registrars-companies-roc-wise-company-master-data and
saved as `registered_companies.csv` in the project root. Downloaded on 26 June 2026.

**What is done with it.** It is used only to attempt an exact, name based match between a
procurement winner and a registered company, to show a corporate identity card for
unambiguous matches. The match is labelled as a likely match to verify.

**Personal data handling.** The email address field is treated as personal data and is
**never displayed or republished**. It is not loaded into any published output. Other
fields (company name, CIN, status, dates, capital, state) are company register
information rather than personal data, although the names of sole proprietors or
individuals, where present, may be personal data.

**Licensing status.** Because this dataset comes from data.gov.in, the Government of
India Open Government Data platform, it is published under the Government Open Data
License India (GODL-India). GODL-India permits reuse, adaptation, and redistribution,
including commercially, provided the source is attributed and the data is not used in a
misleading manner. On that basis the company register fields used here (company name,
CIN, status, incorporation date, paid up capital, state) may be processed and displayed.

Action: confirm GODL-India is the licence stated on the resource page, and add the
required attribution to the Ministry of Corporate Affairs and data.gov.in in the
published tool. The "not in a misleading manner" condition reinforces the project's
existing rule that matches are shown as likely, to verify, and never as accusations.

---

## 3. Derived data produced by Tender Watch

**What it is.** The cleaned and aggregated Parquet tables and summaries built by the ETL
pipeline (for example fact_award, dim_vendor, flag_award, and the sum_ tables).

**Nature.** These are transformations of the two sources above. They contain no new
facts about any party beyond what is in the sources; they re organise and summarise.

**Code licence.** The Tender Watch source code is released under the MIT License (see
LICENSE).

**Data licence. TO CONFIRM.** The licence that can be applied to the derived data
depends entirely on the licences of the two upstream sources in sections 1 and 2. The
derived data cannot be released under more permissive terms than its inputs allow. This
must be resolved once the source licences are confirmed.

---

## 3a. Map boundaries (GeoJSON)

The India choropleth map on the States page uses a state-boundary GeoJSON bundled at
`app/india_states.geojson`, with a `ST_NM` state-name property. It was downloaded from
a public community source (the jbrobst gist commonly used with Plotly for India maps).
It contains geographic boundaries only, no procurement or personal data. The boundaries
are approximate and for visualisation only; they are not an authoritative or political
statement on borders.

## 4. Personal data position (DPDP Act 2023)

India's Digital Personal Data Protection Act 2023 governs the processing of personal
data. Tender Watch's position, to be confirmed with counsel:

- Most of the published content is about organisations and companies, which is not
  personal data.
- Some fields (individual proprietor names, addresses) may be personal data. Much of it
  is already in the public domain through official publication, which is relevant to the
  treatment of publicly available personal data.
- The one clearly sensitive field, the MCA email address, is excluded entirely from all
  published output.
- A correction and removal route is provided in the [DISCLAIMER](../DISCLAIMER.md) so
  that affected individuals can raise concerns.

Action: confirm the DPDP position, in particular the reliance on the publicly available
data treatment and whether any further notice or grievance mechanism is required for a
public instance.

---

## 5. Summary of open items to confirm before a public launch

1. Confirm the licence or terms for the CPPP source data and whether republication is
   permitted.
2. Confirm the terms for using the third party mirror, and record the snapshot date.
3. MCA dataset source is confirmed (data.gov.in, under GODL-India). Remaining: confirm
   the licence stated on the resource page and add the required GODL attribution to the
   Ministry of Corporate Affairs and data.gov.in in the published tool.
4. Determine the licence that can be applied to the derived data, given the above.
5. Confirm the DPDP position and any required grievance mechanism.
6. Have a qualified Indian media and technology lawyer review this document, the
   disclaimer, and the live tool.
