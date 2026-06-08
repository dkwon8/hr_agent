"""
Generate synthetic test resume PDFs for pipeline smoke testing.
Run: python scripts/generate_test_resumes.py
"""

import os
import fitz  # PyMuPDF

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "resumes")

RESUMES = [
    {
        "filename": "alice_chen.pdf",
        "text": """ALICE CHEN
alice.chen@email.com | (617) 555-0101
Boston, MA

LinkedIn: https://linkedin.com/in/alicechen
GitHub: https://github.com/alicechen

EDUCATION
Boston University — B.S. Computer Science
Expected Graduation: May 2026
GPA: 3.7/4.0

SKILLS
Python, Java, Go, Docker, Kubernetes, Linux, Git, REST APIs, PostgreSQL, AWS

EXPERIENCE
Software Engineering Intern — Wayfair (Summer 2025)
- Built microservices in Go handling 10K+ requests per second
- Implemented CI/CD pipelines using GitHub Actions and Docker
- Contributed to internal Kubernetes operator for deployment automation

Research Assistant — BU Systems Lab (Fall 2024 - Present)
- Developing distributed systems benchmarking framework in Python
- Published workshop paper on container orchestration performance

PROJECTS
OpenShift CLI Tool — Open source contributor to oc CLI plugin for log analysis
Cloud Monitor — Real-time Kubernetes cluster monitoring dashboard using React and Go
""",
    },
    {
        "filename": "bob_martinez.pdf",
        "text": """BOB MARTINEZ
bob.martinez@email.com | (919) 555-0202
Raleigh, NC

LinkedIn: https://linkedin.com/in/bobmartinez

EDUCATION
NC State University — B.S. Software Engineering
Expected Graduation: May 2026
GPA: 3.5/4.0

SKILLS
JavaScript, TypeScript, React, Node.js, HTML/CSS, MongoDB, Firebase

EXPERIENCE
Frontend Developer Intern — Local Startup (Summer 2025)
- Built React dashboard for customer analytics
- Integrated Firebase authentication and Firestore database

PROJECTS
Campus Events App — React Native mobile app for NC State events
Portfolio Website — Personal website built with Next.js
""",
    },
    {
        "filename": "carol_johnson.pdf",
        "text": """CAROL JOHNSON
carol.j@email.com | (312) 555-0303
Chicago, IL

EDUCATION
University of Chicago — B.S. Computer Science
Expected Graduation: May 2026
GPA: 3.8/4.0

SKILLS
Python, C++, Machine Learning, TensorFlow, PyTorch, Data Analysis, SQL

EXPERIENCE
Data Science Intern — Citadel (Summer 2025)
- Built ML models for financial time series prediction
- Processed datasets with 100M+ rows using PySpark

PROJECTS
NLP Sentiment Analyzer — BERT-based model for social media sentiment analysis
Autonomous Drone Navigation — Computer vision system using OpenCV and ROS
""",
    },
    {
        "filename": "david_kim.pdf",
        "text": """DAVID KIM
david.kim@email.com | (617) 555-0404
Boston, MA

LinkedIn: https://linkedin.com/in/davidkim99
GitHub: https://github.com/dkim99

EDUCATION
Northeastern University — B.S. Computer Science
Expected Graduation: May 2028
GPA: 3.2/4.0

SKILLS
Python, Java, HTML, CSS

EXPERIENCE
No professional experience yet.

PROJECTS
Calculator App — Simple calculator built in Java for CS101 final project
Personal Blog — WordPress blog about technology
""",
    },
    {
        "filename": "emma_wright.pdf",
        "text": """EMMA WRIGHT
emma.wright@email.com | (617) 555-0505
Boston, MA

LinkedIn: https://linkedin.com/in/emmawright
GitHub: https://github.com/emwright

EDUCATION
MIT — B.S. Electrical Engineering and Computer Science
Expected Graduation: May 2026
GPA: 3.9/4.0

SKILLS
Python, Rust, C, Go, Linux, Containers, Podman, OpenShift, Ansible, Terraform,
Kubernetes, CI/CD, Git, gRPC, PostgreSQL, Redis

EXPERIENCE
Platform Engineering Intern — IBM (Summer 2025)
- Contributed to OpenShift Virtualization operator in Go
- Wrote Ansible playbooks for automated cluster provisioning
- Reduced deployment time by 40% through Tekton pipeline optimization

Open Source Contributor — Kubernetes SIG-CLI (2024 - Present)
- Merged 12 PRs to kubectl and client-go
- Triaged issues and reviewed community contributions

Teaching Assistant — MIT 6.824 Distributed Systems (Spring 2025)
- Helped 200+ students with Raft consensus and MapReduce labs

PROJECTS
Container Runtime — Built a minimal OCI-compliant container runtime in Rust
Service Mesh — Implemented a lightweight Envoy-based service mesh for microservices
""",
    },
]


def create_pdf(text: str, output_path: str):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter size

    # Insert text with a readable font
    text_rect = fitz.Rect(50, 50, 562, 742)
    page.insert_textbox(
        text_rect,
        text.strip(),
        fontsize=10,
        fontname="helv",
        align=fitz.TEXT_ALIGN_LEFT,
    )

    doc.save(output_path)
    doc.close()


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for resume in RESUMES:
        path = os.path.join(OUTPUT_DIR, resume["filename"])
        create_pdf(resume["text"], path)
        print(f"Created: {path}")

    print(f"\nGenerated {len(RESUMES)} test resumes in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
