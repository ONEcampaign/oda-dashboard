# Education
edu_unspecified = list(range(111 * 100, 112 * 100)) + [111]
edu_basic = list(range(112 * 100, 113 * 100)) + [112]
edu_secondary = list(range(113 * 100, 114 * 100)) + [113]
edu_postsec = list(range(114 * 100, 115 * 100)) + [114]

# Health
health_general = list(range(121 * 100, 122 * 100)) + [121]
health_basic = list(range(122 * 100, 123 * 100)) + [122]
health_NCDs = list(range(123 * 100, 124 * 100)) + [123]
pop_RH = list(range(130 * 100, 131 * 100)) + [130]

# Social protection
social_pro = list(range(16010, 16020))
social_services = [16050]
social_other = list(range(16020, 16050)) + list(range(16060, 16100)) + [160]

# other social infrastructure
water_sanitation = list(range(140 * 100, 141 * 100)) + [140]
gov_ps = list(range(152 * 100, 153 * 100)) + [152]

# Government and Civil Society
public_sector = [
    15110,
    15121,
    15122,
    15123,
    15124,
    15126,
    15127,
    15143,
    15144,
    15154,
    15196,
    151,
]
public_finance_m = [15117, 15118, 15119, 15111]
decentral_subnational = [15128, 15129, 15185, 15112]
anticurruption = [15113]
drm = [15116, 15155, 15156, 15114]
public_procurement = [15125]
legal_judicial = [15130, 15131, 15132, 15133, 15134, 15135, 15136, 15137]
macroeconomic_policy = [15142]

democratic_participation = [15150]
elections = [15151]
legislature_political_parties = [15152]
media_free_flow_info = [15153]
human_rights = [15160]
womens_rights = [15170]
ending_violence_women_girls = [15180]
migration = [15190]


# Agriculture, forestry, fishing
agriculture = list(range(311 * 100, 312 * 100)) + [311]
forestry_fishing = list(range(312 * 100, 314 * 100)) + [312, 313]

# Other Economic infrastructure
transport_storage = list(range(210 * 100, 211 * 100)) + [210]
communications = list(range(220 * 100, 221 * 100)) + [220]
banking_financial = list(range(240 * 100, 241 * 100)) + [240]
business = list(range(250 * 100, 251 * 100)) + [250]
industry_mining_const = list(range(321 * 100, 324 * 100)) + [320, 321, 322, 323]
trade_p_r = list(range(331 * 100, 333 * 100)) + [331, 332]
trade_other = [330]

# Energy
energy_policy = [231] + list(range(231 * 100, 232 * 100))
energy_generation_renewable = [232] + list(range(232 * 100, 233 * 100))
energy_generation_nonrenewable = [233] + list(range(233 * 100, 234 * 100))
hybrid_energy_plants = [234] + list(range(234 * 100, 235 * 100))
nuclear_energy_plants = [235] + list(range(235 * 100, 236 * 100))
energy_distribution = [236] + list(range(236 * 100, 237 * 100))

# Environmental Protection
env_policy = [41010]
biosphere_protection = [41020]
bio_diversity = [41030]
site_preservation = [41040]
environment_edu = [41081]
environment_research = [41082]

# Humanitarian
emergency_response = list(range(720 * 100, 721 * 100)) + [720]
reconstruction = list(range(730 * 100, 731 * 100)) + [730]
disaster_prevention = list(range(740 * 100, 741 * 100)) + [740]

# Multi_sector
multi_sector = [43010, 430]
urban_dev = list(range(43030, 43040))
rural_dev = list(range(43040, 43050))
drr = [43060]
other_multi = [43050] + list(range(43070, 431 * 100))

# other
general_budget = list(range(510 * 100, 511 * 100)) + [510]
food_aid = list(range(520 * 100, 521 * 100)) + [520]
commodity_other = list(range(530 * 100, 531 * 100)) + [530]
debt_action_total = list(range(600 * 100, 610 * 100)) + [600]
admin_total = list(range(910 * 100, 911 * 100)) + [910]

refugees = list(range(930 * 100, 931 * 100)) + [930]
unspecified = list(range(998 * 100, 999 * 100)) + [998]


def get_sector_groups():
    return {
        "Education, level unspecified": edu_unspecified,
        "Basic education": edu_basic,
        "Secondary education": edu_secondary,
        "Post-secondary education": edu_postsec,
        "Health, general": health_general,
        "Basic health": health_basic,
        "Non-communicable diseases (NCDs)": health_NCDs,
        "Population policies/programmes & reproductive health": pop_RH,
        "Social protection": social_pro,
        "Multi-sector aid for basic social services": social_services,
        "Water supply & sanitation": water_sanitation,
        "Public sector policy & management": public_sector,
        "Public finance management": public_finance_m,
        "Decentralization & subnational government": decentral_subnational,
        "Anti-corruption organisations and institutions": anticurruption,
        "Domestic resource mobilisation": drm,
        "Public procurement": public_procurement,
        "Legal & judicial development": legal_judicial,
        "Macroeconomic policy": macroeconomic_policy,
        "Democratic participation and civil society": democratic_participation,
        "Legislature & political parties": legislature_political_parties,
        "Media & free flow of information": media_free_flow_info,
        "Elections": elections,
        "Human rights": human_rights,
        "Women's rights organisations, movements, and institutions": womens_rights,
        "Ending violence against women and girls": ending_violence_women_girls,
        "Migration": migration,
        "Conflict peace and security": gov_ps,
        "Other social infrastructure & services": social_other,
        "Agriculture": agriculture,
        "Forestry & fishing": forestry_fishing,
        "Transport & storage": transport_storage,
        "Communications": communications,
        "Energy policy": energy_policy,
        "Energy generation, renewable": energy_generation_renewable,
        "Energy generation, non-renewable": energy_generation_nonrenewable,
        "Hybrid energy plants": hybrid_energy_plants,
        "Nuclear energy plants": nuclear_energy_plants,
        "Energy distribution": energy_distribution,
        "Banking & financial services": banking_financial,
        "Business & other services": business,
        "Industry, mining, construction": industry_mining_const,
        "Trade policies & regulations": trade_p_r,
        "Trade other": trade_other,
        "Environmental policy and admin management": env_policy,
        "Biosphere protection": biosphere_protection,
        "Bio-diversity": bio_diversity,
        "Site- preservation": site_preservation,
        "Environment education/training": environment_edu,
        "Environmental research": environment_research,
        "Emergency response": emergency_response,
        "Reconstruction, relief & rehabilitation": reconstruction,
        "Disaster prevention & preparedness": disaster_prevention,
        "Multi-sector": multi_sector,
        "Urban development": urban_dev,
        "Rural development": rural_dev,
        "Disaster risk reduction": drr,
        "Other multi-sector aid": other_multi,
        "General budget support": general_budget,
        "Developmental food aid/food security assistance": food_aid,
        "Other commodity assistance": commodity_other,
        "Action relating to debt": debt_action_total,
        "Administrative costs of donors": admin_total,
        "Refugees in donor countries": refugees,
        "Unallocated/unspecificed": unspecified,
    }


def get_broad_sector_groups():
    return {
        "Education, level unspecified": "Education",
        "Basic education": "Education",
        "Secondary education": "Education",
        "Post-secondary education": "Education",
        "Health, general": "Health",
        "Basic health": "Health",
        "Non-communicable diseases (NCDs)": "Health",
        "Population policies/programmes & reproductive health": "Health",
        "Social protection": "Social infrastructure, protection and services",
        "Multi-sector aid for basic social services": "Social infrastructure, protection and services",
        "Water supply & sanitation": "Water supply & sanitation",
        "Public sector policy & management": "Government",
        "Public finance management": "Government",
        "Decentralization & subnational government": "Government",
        "Anti-corruption organisations and institutions": "Civil society",
        "Domestic resource mobilisation": "Government",
        "Public procurement": "Government",
        "Legal & judicial development": "Government",
        "Macroeconomic policy": "Government",
        "Democratic participation and civil society": "Civil society",
        "Elections": "Civil society",
        "Legislature & political parties": "Government",
        "Media & free flow of information": "Civil society",
        "Human rights": "Civil society",
        "Women's rights organisations, movements, and institutions": "Civil society",
        "Ending violence against women and girls": "Civil society",
        "Migration": "Government",
        "Conflict peace and security": "Conflict Peace and security",
        "Other social infrastructure & services": "Social infrastructure, protection and services",
        "Agriculture": "Agriculture and forestry & fishing",
        "Forestry & fishing": "Agriculture and forestry & fishing",
        "Transport & storage": "Transport & storage and communications",
        "Communications": "Transport & storage and communications",
        "Energy policy": "Energy",
        "Energy generation, renewable": "Energy",
        "Energy generation, non-renewable": "Energy",
        "Hybrid energy plants": "Energy",
        "Nuclear energy plants": "Energy",
        "Energy distribution": "Energy",
        "Banking & financial services": "Banking & financial services and business",
        "Business & other services": "Banking & financial services and business",
        "Industry, mining, construction": "Industry, mining, construction",
        "Trade policies & regulations": "Trade policies & regulations",
        "Trade other": "Trade policies & regulations",
        "Environmental policy and admin management": "Environment protection",
        "Biosphere protection": "Environment protection",
        "Bio-diversity": "Environment protection",
        "Site-preservation": "Environment protection",
        "Environment education/training": "Environment protection",
        "Environmental research": "Environment protection",
        "Emergency response": "Humanitarian",
        "Reconstruction, relief & rehabilitation": "Humanitarian",
        "Disaster prevention & preparedness": "Humanitarian",
        "Multi-sector": "Multi-sector",
        "Urban development": "Multi-sector",
        "Rural development": "Multi-sector",
        "Disaster risk reduction": "Multi-sector",
        "Other multi-sector aid": "Multi-sector",
        "General budget support": "General budget support",
        "Developmental food aid/food security assistance": "Other",
        "Other commodity assistance": "Other",
        "Null": "Other",
        "Action relating to debt": "Action relating to debt",
        "Administrative costs of donors": "Administrative costs of donors",
        "Refugees in donor countries": "Refugees in donor countries",
        "Unallocated/unspecificed": "Unallocated/unspecificed",
        "Government & civil society": "Government & civil society",
    }