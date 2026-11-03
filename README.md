# eLabFTW Protocol Migrator & Preview Studio

A deterministic, web-based ingestion tool designed to convert legacy wet-lab protocols, notes, and raw data into structured [eLabFTW](https://www.elabftw.net/) entries. 

Built for the Molecular Parasitology Lab, this tool automatically extracts text and tables from standard file formats, repairs scientific notation, and pushes the formatted records directly to your eLabFTW database via REST API v2.

## Features
* **Format Support:** Native extraction for `.docx`, `.pdf`, `.md`, `.txt`, `.xlsx`, and `.csv`. Binary data files (`.png`, `.fcs`, `.zip`, etc.) are automatically queued as attachments.
* **Scientific Notation Repair:** Automatically restores flattened chemical formulas (e.g., H2O → H<sub>2</sub>O) and Unicode/flattened exponents (e.g., 10^6, 10⁶, or 106 cells → 10<sup>6</sup>).
* **Smart Extraction:** Converts native Word and PDF tables to Markdown tables and extracts procedural steps into eLabFTW interactive checklists.
* **Aggregation Modes:** Upload files as individual eLabFTW entries, or merge an entire project folder's worth of notes and data into a single consolidated entry.
* **Zero-Touch Original Attachments:** Automatically uploads your original unmodified `.docx` or `.pdf` file to the `/uploads` section of the new eLabFTW entry for archival safety.

##  How to Use the Tool

### 1. Generate Your eLabFTW API Key
To push records to the database, you need a personal API token.
1. Log into your eLabFTW account.
2. Click your user profile icon (top right) and select **Settings** &rarr; **API Keys**.
3. Create a new key with **Read/Write** permissions. Copy this token.

### 2. Connect and Upload
1. Open the *(https://elabftw-migrator.streamlit.app/)*.
2. In the left sidebar, paste your API Key and click **Connect & Fetch Lab Categories**.
3. Select your target destination (e.g., *Templates* or *Resources*).
4. Upload your files via the **Browser File Upload** tab. 
5. Choose your aggregation mode (Individual vs. Consolidated).

### 3. Preview and Publish
1. Select an entry from the dropdown queue.
2. Inspect the extracted text, tables, and tags in the live simulated eLabFTW card on the right.
3. Edit any formatting in the left column if necessary.
4. Click **Publish Record to eLabFTW** to push the entry, steps, tags, and original attachments directly to the server.

---

### Local Development
To run this tool locally on your own Linux/Windows workstation:
```bash
git clone [https://github.com/figueiredo-lab-gimm/elabftw-migrator.git](https://github.com/figueiredo-lab-gimm/elabftw-migrator.git)
cd elabftw-migrator
pip install -r requirements.txt
streamlit run elab_studio.py
