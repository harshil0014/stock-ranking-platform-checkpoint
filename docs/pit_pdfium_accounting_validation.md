# Independent PDFium accounting validation

The second accounting route uses the PDFium rendering/text engine through
`pypdfium2`. It does not call the existing pypdf locator parser or the
pdfminer/pdfplumber validator. The first route's results are loaded only after
the second extraction has selected its own values, for blind field comparison.

The optional full-document mode uses PDFium text from every report page and
includes adjacent pages only as evidence candidates; it does not combine
unrelated rows or derive ratios. Two complete 179-report runs produced the same
record SHA-256
`d27edbbc3ae6e752dc720ded1496d5a2c8d08d48933cef5d5169afc133f16535`.
The final status counts were eight complete review candidates, seven engine
disagreements, and 164 incomplete records. A row-boundary regression test
specifically prevents a blank ratio row from consuming the next ratio's
percentage values.

Acceptance remains conservative: exact NSE metadata/ISIN/PDF hashes,
standalone basis, FY2025-26 and FY2024-25, direct PAT, direct debt-to-equity
with an issuer definition, and direct ROCE with an issuer definition are all
required. Net-debt ratios, derived values, ambiguous units, blanks, conflicts,
and engine disagreements remain quarantined. A PDFium-only complete record is
only a review candidate; it is never promoted automatically.
