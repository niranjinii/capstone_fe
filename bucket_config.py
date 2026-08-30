CANCER_TYPES = [
    "ACC", "BLCA", "BRCA", "CESC", "CHOL", "COAD", "DLBC", "ESCA",
    "GBM", "HNSC", "KICH", "KIRC", "KIRP", "LAML", "LGG", "LIHC",
    "LUAD", "LUSC", "MESO", "OV", "PAAD", "PCPG", "PRAD", "READ",
    "SARC", "SKCM", "STAD", "TGCT", "THCA", "THYM", "UCEC", "UCS", "UVM"
]

# Development bucket dimensions for instantaneous local testing
BUCKETS = {
    "small": {
        "max_dim": 8,
        "cancers": ["THYM", "GBM", "KICH", "PCPG", "TGCT", "DLBC", "UVM", "PAAD", "LAML", "PRAD"]
    },
    "medium": {
        "max_dim": 16,
        "cancers": [
            "CHOL", "READ", "LIHC", "COAD", "UCS", "THCA", "MESO", "HNSC",
            "OV", "LUAD", "ACC", "STAD", "SKCM", "LGG", "SARC", "KIRP",
            "ESCA", "LUSC", "UCEC", "KIRC"
        ]
    },
    "large": {
        "max_dim": 24,
        "cancers": ["BRCA", "BLCA", "CESC"]
    }
}