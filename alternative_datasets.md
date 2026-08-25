# Alternative Genomic Datasets for Training

> Your current dataset: **TCGA Pan-Cancer (UCSC Xena)** — 33 cancer types, ~10,500 patients, 20,531 genes, RNA-seq (HiSeq V2). Trained via L1-regularised logistic regression.

---

## Why You'd Want a Different Dataset

1. **Cross-dataset validation** — Train on TCGA, test on an independent dataset to prove the model generalises. This is a strong paper claim.
2. **Different cancer scope** — Paediatric cancers (TARGET), cell lines (CCLE), or liquid biopsies (GEO platelet study) test whether the FE system handles different biological domains.
3. **Reviewers will ask** — "Does this only work on TCGA?" is a common question. Having even one cross-validation result is a strong counter.

---

## Recommended Datasets (Verified Usable)

### 1. CCLE / DepMap — Cancer Cell Line Encyclopedia ⭐ BEST ALTERNATIVE
- **What it is:** Gene expression data for **2,100+ human cancer cell lines** across dozens of cancer types. Maintained by the Broad Institute.
- **Format:** Pre-processed CSV matrices. Rows = cell lines, Columns = genes. Ready for `pandas.read_csv()`.
- **Cancer types:** Covers lung, breast, blood, brain, skin, colon, ovarian, pancreatic, and many more.
- **Why it's good for you:**
  - It's NOT a subset of TCGA — it's an entirely independent dataset (cell lines, not patient tumours)
  - Same gene symbol namespace (HGNC), so your existing Lasso pipeline can run with minimal changes
  - The data is already normalised (TPM, log2)
  - CSV download, no bioinformatics preprocessing needed
- **How to download:**
  1. Go to [depmap.org/portal/download](https://depmap.org/portal/download/)
  2. Download `OmicsExpressionAllGenesTPMLogp1Profile.csv` (gene expression matrix)
  3. Download `Model.csv` (metadata with cancer type labels)
  4. Use the `OncotreeLineage` or `OncotreePrimaryDisease` column as your classification label
- **Size:** ~2,100 rows × ~19,000 genes. Similar dimensionality to your TCGA data.
- **Caveat:** Cell lines are not patients — they behave differently biologically. Your models trained on cell lines won't be clinically valid, but they prove the *encryption system* works on independent data.

---

### 2. GEO GSE68086 — Tumor-Educated Platelets ⭐ UNIQUE ANGLE
- **What it is:** RNA-seq from **blood platelets** (not tumour tissue) that can distinguish cancer patients from healthy individuals. 6 cancer types + healthy controls.
- **Cancer types:** Lung, colorectal, pancreatic, glioblastoma, breast, hepatobiliary + healthy.
- **Format:** Pre-cleaned CSV available on Kaggle.
- **Why it's good for you:**
  - Completely different biology from TCGA (liquid biopsy vs tissue biopsy)
  - Demonstrates your system works for non-invasive diagnostics
  - Relatively small (~280 samples), so training is fast
  - Pre-cleaned versions exist
- **How to download:**
  1. Go to [kaggle.com/datasets/kashnitsky/gene-expression-omnibus-geo-dataset-gse68086](https://www.kaggle.com/datasets/kashnitsky/gene-expression-omnibus-geo-dataset-gse68086)
  2. Download the CSV directly
  3. Or programmatically: `from GEOparse import GEOparse; gse = GEOparse.get_GEO("GSE68086")`
- **Caveat:** Only 6 cancer types (vs your 33). But the "platelet-based liquid biopsy" angle is a strong narrative for the paper.

---

### 3. TARGET — Therapeutically Applicable Research to Generate Effective Treatments
- **What it is:** Genomic data for **paediatric and childhood cancers**. Maintained by the NCI on the same GDC portal as TCGA.
- **Cancer types:** Acute Lymphoblastic Leukemia (ALL), Acute Myeloid Leukemia (AML), Neuroblastoma, Osteosarcoma, Wilms Tumour, Kidney Tumour.
- **Format:** Same GDC/Xena format as TCGA. If your notebook parses TCGA Xena files, it can parse TARGET with trivial changes.
- **Why it's good for you:**
  - Same data format and processing pipeline as TCGA — minimal code changes
  - Independent patient cohort (children, not adults)
  - Adds a "paediatric cancer" validation angle
- **How to download:**
  1. Go to [xenabrowser.net/datapages](https://xenabrowser.net/datapages/) and filter for "TARGET"
  2. Download the gene expression matrix (same `EB++` format you already use)
  3. Or via GDC: [portal.gdc.cancer.gov/projects](https://portal.gdc.cancer.gov/projects), filter by "TARGET"
- **Caveat:** Fewer cancer types (~6). Requires GDC authentication for some data tiers.

---

### 4. GTEx — Genotype-Tissue Expression (For Healthy Baseline)
- **What it is:** Gene expression from **healthy tissue** across 50+ tissue types. ~17,000 samples.
- **Why it's useful:** Use it as the "negative control" — train a binary classifier (Cancer vs Healthy) by combining TCGA tumour samples with GTEx normal samples. This is a different classification task than your current cancer-type classifier.
- **How to download:** [gtexportal.org/home/downloads/adult-gtex](https://gtexportal.org/home/downloads/adult-gtex)
- **Caveat:** Requires combining with a cancer dataset, which introduces batch effects. Use with caution.

---

## NOT Recommended

### UCI Machine Learning Repository
- **Why not:** You already know this — it's a **subset of your TCGA dataset** with only 5 cancer types (BRCA, KIRC, COAD, LUAD, PRAD). Training on it would give you less data, fewer cancers, and no new biological insight. It exists for teaching ML, not for research validation.

### ICGC (International Cancer Genome Consortium)
- **Why not (for now):** The legacy portal was **retired in June 2024**. Data still exists but requires DACO (Data Access Compliance Office) approval, SFTP access, and navigating a complex migration to the ARGO platform. Too much bureaucratic overhead for a capstone sprint. Could revisit for a journal submission later.

### MLOmics / TNMplot
- **Why not (for now):** These are aggregation/visualisation tools, not clean downloadable matrices. You'd still need to extract and format the data yourself. Better suited for exploratory analysis than ML training.

---

## My Recommendation

**Start with CCLE/DepMap.** It's the closest match to what you already have:
- Same scale (~2K samples × ~19K genes)
- Clean CSV download
- Independent from TCGA
- Well-known in the ML-for-genomics community

Train your Lasso pipeline on it, save the weights as a second `.npy`, and run the entire FE pipeline on those weights. That gives you a "cross-dataset validation" section in the paper with minimal effort.
