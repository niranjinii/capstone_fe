import os
import numpy as np
import pandas as pd


class PatientStore:
    """Stable interface. Swap subclass to change backend (EHR, Postgres, etc.)."""

    def get_patient_vector(self, patient_id: str) -> np.ndarray:
        raise NotImplementedError

    def patient_exists(self, patient_id: str) -> bool:
        raise NotImplementedError

    def get_patient_label(self, patient_id: str) -> str | None:
        """Return known cancer label if available (for validation, not inference)."""
        return None

    def list_patient_ids(self) -> list[str]:
        """Return all known patient IDs."""
        raise NotImplementedError


class TCGAPatientStore(PatientStore):
    """
    Backed by TCGA-PANCAN-HiSeq-801x20531/ directory.
    - data.csv:   801 rows × 20531 gene expression columns, indexed by sample_0..sample_800
    - labels.csv: 801 rows mapping sample_id -> cancer type (BRCA, COAD, KIRC, LUAD, PRAD)

    Lazy-loads on first access so import is cheap. Subsequent lookups are O(1) from memory.
    """

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._data: pd.DataFrame | None = None
        self._labels: dict[str, str] = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        data_path = os.path.join(self._data_dir, "data.csv")
        labels_path = os.path.join(self._data_dir, "labels.csv")
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"TCGA data not found at {data_path}")
        self._data = pd.read_csv(data_path, index_col=0)
        if os.path.exists(labels_path):
            ldf = pd.read_csv(labels_path, index_col=0)
            self._labels = ldf["Class"].to_dict()
        self._loaded = True

    def patient_exists(self, patient_id: str) -> bool:
        self._load()
        return patient_id in self._data.index

    def get_patient_vector(self, patient_id: str) -> np.ndarray:
        self._load()
        if patient_id not in self._data.index:
            raise KeyError(f"Unknown patient_id: {patient_id!r}")
        return self._data.loc[patient_id].values.astype(np.float32)

    def get_patient_label(self, patient_id: str) -> str | None:
        self._load()
        return self._labels.get(patient_id)

    def list_patient_ids(self) -> list[str]:
        self._load()
        return list(self._data.index)


class XenaPatientStore(PatientStore):
    """
    Backed by the EB++AdjustPANCAN_IlluminaHiSeq_RNASeqV2.geneExp.xena file.
    Format: tab-separated, rows = genes, columns = samples.
    First row = header (sample IDs like TCGA-OR-A5J1-01).
    First column of each row = gene name (format 'SYMBOL|ENTREZ' or just 'SYMBOL').

    Lazy-loads on first access. Transposing a 20531-gene file takes ~10s the first
    time; subsequent lookups are O(1) from memory.
    """

    def __init__(self, xena_path: str):
        self._path = xena_path
        self._data: 'pd.DataFrame | None' = None   # samples × genes after transpose
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        import pandas as pd

        cache_npy  = self._path + ".cache.npy"
        cache_meta = self._path + ".cache.meta.json"

        if os.path.exists(cache_npy) and os.path.exists(cache_meta):
            # Fast path: load binary cache (~2s vs ~60s for the raw TSV)
            import json as _json
            print("[PatientStore] Loading from binary cache...")
            with open(cache_meta, "r") as f:
                meta = _json.load(f)
            values = np.load(cache_npy)
            self._data = pd.DataFrame(
                values,
                index=meta["index"],
                columns=meta["columns"],
            )
        else:
            # Slow path: parse raw TSV and build cache for next time
            import json as _json
            print("[PatientStore] First run — parsing Xena file (~60s). Cache will be built for next time...")
            df = pd.read_csv(self._path, sep='\t', index_col=0)
            self._data = df.T.astype('float32')
            # Drop the 'sample' header row that comes from the gene-name column label
            if 'sample' in self._data.index:
                self._data = self._data.drop(index='sample')
            # Clean up gene names: 'TP53|7157' -> 'TP53'
            self._data.columns = [
                c.split('|')[0] if '|' in str(c) else str(c)
                for c in self._data.columns
            ]
            # Save binary cache
            print("[PatientStore] Saving binary cache for future runs...")
            np.save(cache_npy, self._data.values)
            with open(cache_meta, "w") as f:
                _json.dump({
                    "index":   list(self._data.index),
                    "columns": list(self._data.columns),
                }, f)
            print("[PatientStore] Cache saved.")

        self._loaded = True
        print(f"[PatientStore] Ready: {len(self._data)} patients x {len(self._data.columns)} genes.")


    def patient_exists(self, patient_id: str) -> bool:
        self._load()
        return patient_id in self._data.index

    def get_patient_vector(self, patient_id: str) -> 'np.ndarray':
        self._load()
        if patient_id not in self._data.index:
            raise KeyError(f"Unknown patient_id: {patient_id!r}")
        return self._data.loc[patient_id].values

    def get_patient_label(self, patient_id: str) -> 'str | None':
        # TCGA barcodes encode cancer type: TCGA-OR-... = ACC, TCGA-A8-... = BRCA, etc.
        # We don't have a separate labels file for this dataset, so return None.
        return None

    def list_patient_ids(self) -> list[str]:
        self._load()
        return list(self._data.index)
