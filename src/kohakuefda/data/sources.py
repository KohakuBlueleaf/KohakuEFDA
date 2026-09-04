"""Where the game tables come from and which tables the dataset needs."""

AKEDATA_MANIFEST_URL = "https://data.akedata.wiki/manifest.json"
AKEDATA_BASE_URL = "https://data.akedata.wiki/"
MIRROR_REPO = "555me/beyondGameData"
MIRROR_RAW_URL = (
    "https://raw.githubusercontent.com/555me/beyondGameData/{ref}/tableCfg/{table}.json"
)
MIRROR_COMMITS_URL = "https://api.github.com/repos/555me/beyondGameData/commits"
WIKI_API_URL = "https://endfield.wiki.gg/api.php"
USER_AGENT = "KohakuEFDA/0.0.1 (+https://github.com/KohakuBlueleaf/KohakuEFDA)"

FACTORY_TABLES: tuple[str, ...] = (
    "FactoryBuildingTable",
    "FactoryBuildingTypeTable",
    "FactoryMachineCraftTable",
    "FactoryMachineCraftGroupTable",
    "FactoryMachineCrafterTable",
    "FactoryMachineCraftModeTable",
    "FactoryItemTable",
    "FactoryGridBeltTable",
    "FactoryLiquidPipeTable",
    "FactoryGridRouterTable",
    "FactoryLiquidRouterTable",
    "FactoryGridConnecterTable",
    "FactoryLiquidConnectorTable",
    "FactoryBoxValveTable",
    "FactoryFluidValveTable",
    "FactoryUndergroundPipeTable",
    "FactoryConst",
    "FacBlueprintConst",
    "FactoryHubTable",
    "FactoryPowerStationTable",
    "FactoryPowerPoleTable",
    "FactoryFuelItemTable",
    "FactoryMinerTable",
    "FactoryStoragerTable",
    "FactoryFluidPumpInTable",
    "FactoryGasMinerTable",
    "FactoryTransmuterTable",
    "FactoryVaporizerTable",
    "FactoryFluidConsumeTable",
    "FactoryFluidConsumeItemTable",
    "FactorySewageTreatImportTable",
    "FactorySewageTreatExportTable",
    "FacSTTBuildingDomainLimitTechTable",
    "FacSTTNodeTable",
    "FacSTTLayerTable",
    "FacSTTCategoryTable",
    "FactoryPanelStoreTable",
    "DomainDataTable",
    "MapIdTable",
    "LevelDescTable",
    "ItemTable",
)
