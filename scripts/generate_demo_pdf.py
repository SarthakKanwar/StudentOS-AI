#!/usr/bin/env python3
"""Generate the synthetic demo handbook.

Entirely fabricated (ADR-010). No real university data is used anywhere.

Pages are deliberately dense: a sparse document collapses into a single chunk
spanning every page, and a citation reading "pp.1-4" demonstrates nothing. Real
handbook pages carry 600+ words, which is what makes page-level citation useful.
"""

import sys
import textwrap
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PAGES = [
    (
        "Computer Science Department - Student Handbook, Autumn 2026",
        """SECTION 1 - COURSE INFORMATION

CS-402 Computer Networks is a core third-year course worth 4 credits. It is taught by Dr. Amrita Nair and meets on Mondays and Thursdays from 10:00 to 11:30 in Lecture Hall B. The course carries a weekly laboratory session on Wednesdays from 15:00 to 17:00 in Networking Laboratory 2, where students configure routers, capture traffic and analyse protocol behaviour. Laboratory attendance is recorded separately from lecture attendance and both must independently satisfy the departmental minimum.

CS-311 Database Systems is a core second-year course worth 3 credits. It is taught by Dr. Vikram Sethi and meets on Tuesdays and Fridays from 14:00 to 15:30 in Lecture Hall D. The course includes a term project in which students design, normalise and implement a relational schema for a problem of their choosing, subject to approval by the instructor before the end of week four.

CS-455 Machine Learning is a fourth-year elective worth 4 credits, taught by Dr. Priya Raman on Wednesdays from 09:00 to 12:00 in Lecture Hall A. Students must have completed CS-311 Database Systems and MA-201 Linear Algebra before enrolling. Enrolment is capped at sixty students and places are allocated by cumulative grade point average. Students who are not allocated a place are added to a waiting list in rank order and are informed within five working days of the enrolment deadline.

CS-210 Data Structures is a second-year core course worth 4 credits, taught by Dr. Sanjay Iyer on Mondays, Wednesdays and Fridays from 11:45 to 12:45 in Lecture Hall C. It is a prerequisite for CS-402 Computer Networks and for CS-455 Machine Learning.

Course registration for the Autumn 2026 semester opens on 3 August 2026 and closes on 21 August 2026. Late registration is permitted until 28 August 2026 on payment of a late fee of 1,500 rupees. No registration is accepted after 28 August 2026 under any circumstances. Students may drop a course without academic penalty until 11 September 2026; a course dropped after that date is recorded as a withdrawal on the transcript.""",
    ),
    (
        "SECTION 2 - EXAMINATION SCHEDULE AND RULES",
        """End-term examinations for the Autumn 2026 semester are held in the Examination Block according to the following schedule.

CS-402 Computer Networks: 14 December 2026, 10:00 to 13:00, Examination Hall 1.

CS-311 Database Systems: 16 December 2026, 10:00 to 13:00, Examination Hall 2.

CS-455 Machine Learning: 18 December 2026, 14:00 to 17:00, Examination Hall 1.

CS-210 Data Structures: 20 December 2026, 10:00 to 13:00, Examination Hall 3.

Students must arrive at the examination hall at least thirty minutes before the scheduled start time. Candidates arriving more than thirty minutes after the start time are not admitted and are recorded as absent. No candidate may leave the hall during the first sixty minutes or the final fifteen minutes of any examination.

Students must carry their institute identity card to every examination. A candidate without an identity card may be permitted to sit the paper at the invigilator's discretion but must present the card at the department office within twenty-four hours, failing which the paper is not evaluated.

Permitted materials are limited to pens, pencils, and a non-programmable calculator. Mobile telephones, smart watches and any device capable of storing or transmitting information are prohibited inside the examination hall. Possession of a prohibited device, whether or not it is used, is treated as an instance of examination misconduct and is referred to the Examination Committee.

Re-examinations for students who fail a course are scheduled in the second week of January 2027. A re-examination fee of 500 rupees per paper applies and must be paid before 5 January 2027. A student may attempt a re-examination for a maximum of two courses in any one semester. The grade awarded in a re-examination is capped at the minimum passing grade regardless of the marks obtained.

Requests for revaluation of an end-term answer script must be submitted within ten working days of the publication of results, accompanied by a fee of 750 rupees per paper. The revised mark stands as final whether it is higher or lower than the original.""",
    ),
    (
        "SECTION 3 - SYLLABUS TOPICS FOR CS-402 COMPUTER NETWORKS",
        """The CS-402 Computer Networks syllabus is organised into five units, each carrying approximately equal weight in the end-term examination.

Unit 1 - Foundations. The OSI seven-layer reference model and the TCP/IP four-layer model, and the correspondence between them. Physical layer fundamentals including bandwidth, latency, throughput and the distinction between them. Transmission media: twisted pair, coaxial cable, optical fibre and wireless. Encoding schemes including NRZ, Manchester and 4B/5B. Multiplexing techniques covering frequency division, time division and wavelength division.

Unit 2 - Data Link Layer. Framing methods including character count, byte stuffing and bit stuffing. Error detection using parity, checksums and cyclic redundancy checks. Error correction using Hamming codes. Flow control protocols: stop and wait, go back N, and selective repeat. The medium access control sublayer, covering ALOHA, slotted ALOHA, CSMA, CSMA/CD and CSMA/CA. Ethernet frame format and switched Ethernet. Virtual local area networks and the 802.1Q tag.

Unit 3 - Network Layer. IPv4 addressing, classful and classless addressing, subnetting and supernetting. Variable length subnet masking and CIDR notation. The IPv4 header in detail including fragmentation and the time to live field. IPv6 addressing and the motivation for the transition. Address resolution using ARP, and dynamic address assignment using DHCP. Routing algorithms: distance vector routing and the count to infinity problem, link state routing and Dijkstra's algorithm, and hierarchical routing. Interior and exterior gateway protocols including RIP, OSPF and BGP. Network address translation.

Unit 4 - Transport Layer. The distinction between connection-oriented and connectionless service. User Datagram Protocol and its appropriate uses. Transmission Control Protocol in detail: the three-way handshake, connection termination, sequence and acknowledgement numbers, and the sliding window. Flow control versus congestion control. TCP congestion control including slow start, congestion avoidance, fast retransmit and fast recovery. Timer management and retransmission timeout estimation.

Unit 5 - Application Layer and Security. The domain name system, its hierarchy, resource record types and resolution process. Hypertext Transfer Protocol including persistent connections, caching and the differences introduced by HTTP/2. Electronic mail protocols: SMTP, POP3 and IMAP. File transfer using FTP. An introduction to network security covering symmetric and asymmetric cryptography, digital signatures, certificates and the Transport Layer Security handshake. Common attacks including spoofing, replay and denial of service.""",
    ),
    (
        "SECTION 4 - ATTENDANCE, ASSESSMENT AND ACADEMIC CONDUCT",
        """Attendance requirement.

Students must maintain a minimum of 75 percent attendance in every registered course, calculated separately for lectures and for laboratory sessions where a course has both. A student whose attendance in a course falls below 75 percent is not permitted to sit the end-term examination for that course and is recorded as detained. A detained student must repeat the course in a subsequent semester.

Attendance is recorded at the start of each session. A student who arrives after attendance has been taken is marked absent for that session, and the instructor is under no obligation to amend the record afterwards.

Medical leave may be granted on production of a certificate from a registered medical practitioner, submitted to the department office within seven days of the student returning to classes. Approved medical leave may raise a student's effective attendance by at most 10 percentage points. A student whose raw attendance is below 65 percent therefore cannot reach the threshold by medical leave alone.

Students representing the institute at approved sporting or cultural events may apply for duty leave in advance through the Office of Student Affairs. Duty leave is subject to the same 10 percentage point ceiling as medical leave, and the two cannot be combined to exceed that ceiling.

Assessment weighting.

Internal assessment counts for 40 percent of the final grade in every course and the end-term examination counts for the remaining 60 percent. Internal assessment comprises two class tests worth 15 percent each and assignments worth 10 percent in total. Class tests are held in the sixth and eleventh weeks of the semester.

A student must score at least 40 percent in the end-term examination in order to pass a course, irrespective of the marks obtained in internal assessment. A student who meets the internal assessment threshold but scores below 40 percent in the end-term examination is recorded as having failed the course and must appear for the re-examination.

Academic conduct.

Plagiarism in any assignment or project is treated as academic misconduct. A first instance results in a mark of zero for the work concerned and a written warning placed on the student's record. A second instance results in failure of the entire course and referral to the Academic Disciplinary Committee. Collaboration on assignments is permitted only where the assignment brief explicitly states that it is a group submission.""",
    ),
]


def render_page(heading: str, body: str) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    c.setFont("Helvetica-Bold", 11.5)
    c.drawString(54, 744, heading)

    c.setFont("Helvetica", 8.6)
    y = 724
    line_height = 11.4

    for paragraph in body.split("\n\n"):
        for line in textwrap.wrap(paragraph.strip(), width=104):
            if y < 52:
                break
            c.drawString(54, y, line)
            y -= line_height
        y -= 5

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def main() -> int:
    writer = PdfWriter()
    for heading, body in PAGES:
        reader = PdfReader(BytesIO(render_page(heading, body)))
        for page in reader.pages:
            writer.add_page(page)

    out_dir = Path(__file__).resolve().parent.parent / "sample-data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "cs-department-handbook.pdf"

    buffer = BytesIO()
    writer.write(buffer)
    out_path.write_bytes(buffer.getvalue())

    print(f"[OK] Wrote {out_path} ({len(PAGES)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
