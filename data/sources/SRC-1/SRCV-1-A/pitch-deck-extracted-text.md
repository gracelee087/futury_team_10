# SRCV-1-A — Derived extraction (NOT the original; original = Futury-Hackathon-2026-Englisch.pdf)

- Derivation: PyMuPDF `page.get_text()` over the original PDF, 2026-10-26, T10-035.
- Fidelity: page text is verbatim from the PDF text layer; the `===== PAGE n =====`
  separators and this header are the only additions. Slide ordering/bullets follow the
  text layer, which may flatten layout.
- Purpose: makes the client requirement statements (pp. 8, 10, 11) machine-checkable for
  the T10-035 finding. The immutable original is authoritative.

===== PAGE 1 =====
FUTURY
AI review assistant for system review
Team 10

===== PAGE 2 =====
AI-powered system review

===== PAGE 3 =====
AI review assistant for system review

===== PAGE 4 =====
AI review assistant for system review

===== PAGE 5 =====
AI review assistant for system review
About the ITSG – what do we do?

===== PAGE 6 =====
6
23.10.2026
AI review assistant for system review
System review – what is it?
▪Systems = payroll programs
(SAP, Datev, Lexware etc.)
▪€400 billion in social insurance
contributions
▪800 million messages
exchanged per year
▪
proof of contributions
▪
sick notes
▪
registration and deregistration
▪
income replacement benefits
▪
...

===== PAGE 7 =====
7
23.10.2026
AI review assistant for system review
System review – what is it?
▪
Objective: To ensure that social
insurance contributions are
calculated correctly and
messages are transmitted
correctly.
▪
Specifications spread across 100
documents.
▪
Before the initial approval of a
system, we provide intensive
consultation and testing of the
entire software.
▪
This is followed by an annual
quality control (audit).

===== PAGE 8 =====
8
23.10.2026
AI review assistant for system review
Our legal mandate
Book IV of the Code of Social Law (SGB) - Common provisions for social insurance -
(Article I of the Act of 23 December 1976, Federal Law Gazette I p. 3845) - Section 95b
System Review
(1) Persons subject to reporting obligations shall submit reports and proof of contributions by means of data transmission from
system-tested programs or system-tested electronic filling aids. This shall also apply to applications and certificates, insofar as
this is regulated under this Code or the Expenditure Compensation Act. . . .
(2) A system review shall be carried out for programs and electronic filling aids used for the exchange of data between persons
subject to reporting obligations and the social security institutions and other accepting bodies pursuant to subsection (1). The
system review shall include advice as well as the professional and technical examination of the application software for the
recording, testing, administration, calculation and processing as well as the transmission, acceptance or retrieval of the
necessary data. Payroll accounting programs shall carry out the calculations and the generation of data as well as their
verification by machine; Filling aids shall support manual calculations by electronically transmitting and storing the data. . . .
(3) The hardware belonging to the information technology infrastructure of a reporting party, the operating systems and the
internal communication software are not part of the system audit.
(4) The system review shall be carried out by the National Association of Health Insurance Funds with the participation of the
pension insurance institutions, the accident insurance institutions and the Federal Employment Agency on behalf of all the
umbrella organisations of the social insurance institutions and the Working Group of Professional Pension Institutions.
. . .
Source: § 95b SGB 4 - paragraph 2

===== PAGE 9 =====
9
23.10.2026
AI review assistant for system review
The Challenge
Design an AI solution that supports and
potentially even replaces the testing
processes.
For this challenge, focus on the payroll
process for income replacement benefits
("Entgeltersatzleistungen")
e.g. maternity benefit and sickness benefit.
It is intended to automatically check
whether a program meets all applicable
specifications within this scope.
The AI solution is intended to offer different
technical approaches.

===== PAGE 10 =====
10
23.10.2026
AI review assistant for system review
How it could work
1. AI generates technical test cases.
2. Humans perform test cases in
payroll software.
3. AI checks the data sets generated in the
process.
Optional: The AI review assistant is set up locally by the software vendor who then tests
the application. The AI review assistant generates a test report for the ITSG system review.

===== PAGE 11 =====
11
23.10.2026
AI review assistant for system review
Objectives: What should the AI review assistant be
able to do?
▪
Identifythe relevant requirements from the specifications
▪
Translate the requirements into testable criteria
▪
Generate test cases with expected results
▪
Createa traceable test record
▪
Test the payroll software with the test casesand comparethe results with
the expected results
▪
Delivercomprehensible test reports

===== PAGE 12 =====
12
23.10.2026
AI review assistant for system review
The cherry on top
As an optional extension, build a
prototype based on your concept.
The prototype can be implemented as a
code demonstrator, app, website or in
another suitable form, provided that it
is clearly recognizable how the solution
supports the system review process.

===== PAGE 13 =====
13
23.10.2026
AI review assistant for system review
If you have any questions, we are happy to help you
Gregor Grebe, Chief Strategy
Officer, ITSG GmbH
Thorsten Müller, Group Leader
Strategy, ITSG GmbH
Gerald Friedrich, System
Examiner, ITSG GmbH
