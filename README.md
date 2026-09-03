\# LinkedIn AI Networking Assistant



A local Python automation assistant that detects newly accepted LinkedIn connections from Gmail, identifies whether the connection is a founder or employee, performs company/job research, generates personalized networking messages, and sends them to Telegram for approval.



The final LinkedIn message is intentionally sent manually.



\---



\## What It Does



The assistant monitors LinkedIn connection-acceptance emails through Gmail.



The workflow is:



```text

LinkedIn Connection Accepted

&#x20;       ↓

Gmail detects acceptance email

&#x20;       ↓

Extract person information

&#x20;       ↓

OpenRouter classification

&#x20;       ↓

Founder or Employee?

&#x20;       ↓

&#x20;┌───────────────┬─────────────────┐

&#x20;│ Founder       │ Employee        │

&#x20;↓               ↓

Research company Search company jobs

&#x20;↓               ↓

Understand       Filter relevant

product/company  AI/Data/ML roles

&#x20;↓               ↓

Match skills     Experience <=3 yrs?

&#x20;↓               ↓

Generate         Generate referral

contribution     request only when

message          verified job exists

&#x20;└───────────────┴─────────────────┘

&#x20;       ↓

SQLite

&#x20;       ↓

Telegram Approval

&#x20;       ↓

\[✅ APPROVE] \[❌ SKIP]

&#x20;       ↓

Approved message displayed

&#x20;       ↓

Open LinkedIn

&#x20;       ↓

Manual review / paste / send

```



\---



\# Features



\* Gmail OAuth integration

\* Detects LinkedIn connection acceptance emails

\* Extracts:



&#x20; \* Name

&#x20; \* Headline

&#x20; \* LinkedIn profile URL

\* Duplicate email protection

\* SQLite persistence

\* OpenRouter LLM integration

\* Founder vs employee classification

\* Web-based company research

\* Employee job research

\* AI/Data/ML/MLOps/DevOps job filtering

\* Maximum experience requirement of 3 years

\* Evidence-based job verification

\* Founder contribution-focused messages

\* Employee referral messages

\* Telegram approval interface

\* Approve / Skip callback handling

\* LinkedIn profile/message shortcut

\* One-command launcher

\* Configurable Gmail polling interval



\---



\# Employee Workflow



For employees:



```text

Connection accepted

↓

Identify company

↓

Search current company vacancies

↓

Look for:



AI Engineer

ML Engineer

Machine Learning Engineer

Data Engineer

Data Scientist

MLOps Engineer

DevOps Engineer

Cloud Engineer

GenAI Engineer

LLM Engineer



↓

Verify experience requirement

↓

<= 3 years?

```



If a suitable verified vacancy exists:



```text

matching\_job\_found = true

↓

Generate referral request

↓

Telegram approval

```



Example message:



```text

Hi Abhishek,



I noticed Encora is actively hiring for AI Engineering roles. I have 3 years of experience in production AI/ML and data engineering (portfolio: https://srinivassivakumar.github.io/).



I'd be grateful for a referral, or if you could connect me with the right hiring contact or team for these roles.



Regards,



Srinivas Sivakumar

```



If no verified suitable job exists:



```text

matching\_job\_found = false

status = no\_matching\_job

```



The system does not invent a vacancy or send a referral request.



\---



\# Founder Workflow



For founders:



```text

Connection accepted

↓

Identify company

↓

Research company

↓

Understand product/platform

↓

Match relevant technical skills

↓

Generate contribution-focused message

↓

Telegram approval

```



Example:



```text

Hi Uday,



I really liked OnIT India’s idea of turning user intent into executable tasks.



I work on Agentic AI and could help with task agents, matching, ranking and marketplace analytics.



Are you currently looking for someone on the AI/data engineering side as the platform grows?



Portfolio: https://srinivassivakumar.github.io/



Regards,

Srinivas Sivakumar

```



Company claims and contribution suggestions are generated only from available research evidence.



\---



\# Telegram Approval



A founder may produce a card similar to:



```text

🚀 NEW FOUNDER CONNECTION



Name

Founder @ Company



Suggested message:

...



\[✅ APPROVE] \[❌ SKIP]

\[👤 LINKEDIN] \[🌐 COMPANY]

```



An employee with a verified job may produce:



```text

🔔 NEW CONNECTION



Name

Employee @ Company



Matching vacancy:

AI Engineer



Experience:

1-3 years



Match:

86%



Suggested referral message:

...



\[✅ APPROVE] \[❌ SKIP]

\[👤 LINKEDIN] \[💼 JOB]

```



Pressing \*\*APPROVE\*\*:



```text

DB status → approved

↓

Telegram displays final message

↓

OPEN LINKEDIN button

```



The assistant does \*\*not automatically click Send on LinkedIn\*\*.



\---



\# Project Structure



Approximate structure:



```text

linkedin-ai-assistant/

│

├── app/

│   ├── db.py

│   ├── models.py

│   └── services/

│       ├── connection\_processor.py

│       ├── connection\_repository.py

│       ├── gmail\_service.py

│       ├── openrouter\_service.py

│       ├── telegram\_service.py

│       └── web\_search\_service.py

│

├── data/

│

├── secrets/

│

├── linkedin\_email\_parser.py

├── save\_connections.py

├── telegram\_callback\_worker.py

├── worker.py

├── run\_assistant.py

├── mark\_existing\_emails\_processed.py

│

├── test\_ai\_connection.py

├── test\_connection\_processor.py

├── test\_database.py

├── test\_existing\_connection\_pipeline.py

├── test\_single\_connection\_pipeline.py

├── test\_telegram\_approval.py

├── test\_web\_search.py

│

├── .env.example

├── .gitignore

└── README.md

```



\---



\# Requirements



Recommended:



\* Python 3.11+

\* Gmail account

\* Google Cloud OAuth Desktop credentials

\* Telegram bot

\* OpenRouter API key



Install dependencies:



```powershell

pip install requests python-dotenv

pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

pip install beautifulsoup4

pip install -U ddgs

```



\---



\# Setup



\## 1. Clone repository



```powershell

git clone https://github.com/srinivassivakumar/linkedinnotification.git

cd linkedinnotification

```



\## 2. Create virtual environment



Windows:



```powershell

python -m venv .venv

```



Activate it:



```powershell

.\\.venv\\Scripts\\Activate.ps1

```



\---



\## 3. Install dependencies



```powershell

pip install requests python-dotenv

pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

pip install beautifulsoup4

pip install -U ddgs

```



\---



\## 4. Create `.env`



Copy:



```text

.env.example

```



to:



```text

.env

```



Then configure:



```env

OPENROUTER\_API\_KEY=...

OPENROUTER\_MODEL=openrouter/free



TELEGRAM\_BOT\_TOKEN=...

TELEGRAM\_CHAT\_ID=...



GMAIL\_LABEL=LinkedInAccepted

GMAIL\_POLL\_SECONDS=60



DATABASE\_URL=sqlite:///data/linkedin\_assistant.db



APPROVAL\_SECRET=...

```



Never commit `.env`.



\---



\# Gmail Setup



Create a Google Cloud project.



Enable Gmail API.



Create OAuth credentials:



```text

Application type: Desktop app

```



Required Gmail scope:



```text

https://www.googleapis.com/auth/gmail.readonly

```



Download the OAuth client credentials file.



Store it locally as:



```text

secrets/credentials.json

```



The first Gmail authentication will create:



```text

secrets/token.json

```



Neither file should be committed to GitHub.



Create a Gmail label:



```text

LinkedInAccepted

```



Recommended Gmail filter:



```text

from:invitations@linkedin.com subject:"Your invitation has been accepted"

```



Apply the label:



```text

LinkedInAccepted

```



\---



\# Telegram Setup



Create a bot using Telegram BotFather.



Add the following to `.env`:



```env

TELEGRAM\_BOT\_TOKEN=...

TELEGRAM\_CHAT\_ID=...

```



The assistant uses Telegram inline buttons for approval.



\---



\# Database



SQLite is used locally.



Create the database:



```powershell

python app\\db.py

```



The database is stored under:



```text

data/linkedin\_assistant.db

```



Database files are intentionally excluded from Git.



\---



\# Running the Assistant



Start the complete application with:



```powershell

python .\\run\_assistant.py

```



This starts both:



```text

Gmail Worker

\+

Telegram Callback Worker

```



The Gmail worker currently checks every:



```text

60 seconds

```



Configure this with:



```env

GMAIL\_POLL\_SECONDS=60

```



Stop everything using:



```text

Ctrl + C

```



\---



\# Running Once Per Day



The assistant does not need to run continuously.



You can start:



```powershell

python .\\run\_assistant.py

```



once per day.



It will scan Gmail for new, previously unprocessed LinkedIn acceptance emails.



After processing them and receiving Telegram notifications, the program can be stopped with:



```text

Ctrl + C

```



\---



\# Security



Never commit:



```text

.env

secrets/credentials.json

secrets/token.json

data/\*.db

```



The repository's `.gitignore` excludes these files.



If an API token has ever been exposed publicly, rotate it immediately.



\---



\# Important Design Decision



The assistant intentionally does not automate LinkedIn's final \*\*Send\*\* action.



Approval means:



```text

Message approved

↓

Open LinkedIn

↓

Human reviews/pastes message

↓

Human presses Send

```



This keeps the final outreach action under manual control.



\---



\# Portfolio



Srinivas Sivakumar



AI, Data \& DevOps Engineer



https://srinivassivakumar.github.io/



