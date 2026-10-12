"""
Sector-Specific Operational KPIs for All 22 Companies.

Each sector has distinct KPI structures reflecting industry-specific metrics
that credit analysts use for appraisal. These flow into:
  - Section 12 (Detailed Operational Analysis)
  - Section 13 (Financial Projections) — sector-specific projection logic
  - Source attribution across CAM tables
"""

# ═══════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE — ADPT001, NTPC001, PINF001, PNCR001
# ═══════════════════════════════════════════════════════════════════════════════

ADPT001_SECTOR_KPIS = {
    "sector_type": "ports_logistics",
    "cargo_throughput": {
        "total_cargo_mmt_fy25": 407.2,
        "total_cargo_mmt_fy24": 370.5,
        "total_cargo_mmt_fy23": 339.8,
        "container_cargo_mmt_fy25": 129.4,
        "dry_bulk_mmt_fy25": 168.3,
        "liquid_bulk_mmt_fy25": 109.5,
        "container_teu_mn_fy25": 9.45,
        "source": "Company Annual Report; Port Operator Returns"
    },
    "port_assets": {
        "total_ports": 14,
        "total_terminals": 36,
        "total_berths": 90,
        "operational_capacity_mmt": 620,
        "capacity_utilization_pct": 65.7,
        "avg_turnaround_time_hrs": 1.82,
        "avg_rake_handling_time_hrs": 4.5,
        "source": "Company Disclosure; Indian Ports Association"
    },
    "logistics_network": {
        "inland_container_depots": 11,
        "warehousing_capacity_msf": 4.8,
        "rail_fleet_rakes": 120,
        "truck_fleet": 5200,
        "multimodal_connectivity": True,
        "source": "Company Operational Data"
    },
    "concession_profile": {
        "avg_residual_concession_years": 22,
        "total_concession_value_cr": 58000,
        "longest_concession_years": 50,
        "govt_stake_pct": 0,
        "source": "Concession Agreements; Annual Report"
    },
    "development_projections": {
        "capex_plan_fy26_cr": 12500,
        "capex_plan_fy27_cr": 15000,
        "target_capacity_mmt_fy28": 750,
        "projected_cargo_fy26_mmt": 440,
        "projected_cargo_fy27_mmt": 480,
        "projected_revenue_fy26_cr": 29800,
        "projected_revenue_fy27_cr": 34500,
        "source": "Company Guidance; Analyst Presentations"
    }
}

NTPC001_SECTOR_KPIS = {
    "sector_type": "power_generation",
    "generation_capacity": {
        "installed_capacity_mw": 73974,
        "coal_capacity_mw": 55774,
        "gas_capacity_mw": 5264,
        "renewable_capacity_mw": 3424,
        "hydro_capacity_mw": 2012,
        "nuclear_jv_mw": 1500,
        "group_installed_mw": 76135,
        "source": "Company Annual Report; CEA Monthly Data"
    },
    "operational_performance": {
        "plf_pct_fy25": 75.8,
        "plf_pct_fy24": 74.2,
        "plf_pct_fy23": 72.1,
        "national_avg_plf_pct": 65.4,
        "generation_bu_fy25": 384.5,
        "generation_bu_fy24": 372.8,
        "generation_bu_fy23": 359.2,
        "avg_tariff_per_unit_rs": 4.15,
        "fuel_cost_per_unit_rs": 2.28,
        "availability_factor_pct": 92.3,
        "auxiliary_consumption_pct": 7.2,
        "heat_rate_kcal_kwh": 2375,
        "source": "Company Annual Report; CEA Thermal Performance Review"
    },
    "fuel_security": {
        "coal_linkage_coverage_pct": 95,
        "captive_coal_mines": 12,
        "captive_coal_production_mt_fy25": 32.5,
        "total_coal_requirement_mt": 210,
        "avg_coal_cost_per_ton_rs": 2850,
        "coal_stock_days": 18,
        "source": "Coal Ministry Data; Company Disclosure"
    },
    "renewable_expansion": {
        "re_target_mw_fy32": 60000,
        "re_pipeline_mw": 25000,
        "green_hydrogen_pilot_mw": 250,
        "ev_charging_stations": 450,
        "source": "Company RE Strategy; MNRE Data"
    },
    "development_projections": {
        "capex_plan_fy26_cr": 27500,
        "capex_plan_fy27_cr": 32000,
        "target_capacity_mw_fy28": 85000,
        "projected_generation_bu_fy26": 405,
        "projected_revenue_fy26_cr": 195000,
        "projected_revenue_fy27_cr": 215000,
        "source": "Company Guidance; MoP Capacity Plan"
    }
}

PINF001_SECTOR_KPIS = {
    "sector_type": "road_construction",
    "order_book": {
        "total_order_book_cr": 8500,
        "book_to_bill_ratio": 3.9,
        "epc_orders_cr": 5200,
        "bot_ham_orders_cr": 3300,
        "orders_received_fy25_cr": 2100,
        "executable_order_book_cr": 6800,
        "source": "Company Annual Report"
    },
    "project_pipeline": [
        {"project_name": "NH-48 Bangalore-Hubli (Pkg-3)", "length_km": 134, "contract_value_cr": 2150, "completion_pct": 72, "model": "EPC", "client": "NHAI", "target_completion": "Q3 FY2026"},
        {"project_name": "Eastern Peripheral Expressway Ext", "length_km": 86, "contract_value_cr": 1650, "completion_pct": 28, "model": "HAM", "client": "NHAI", "target_completion": "Q2 FY2028"},
        {"project_name": "Solapur-Bijapur 4-lane", "length_km": 98, "contract_value_cr": 1480, "completion_pct": 45, "model": "EPC", "client": "MoRTH", "target_completion": "Q4 FY2027"},
    ],
    "execution_metrics": {
        "km_executed_fy25": 180,
        "km_executed_fy24": 205,
        "km_executed_fy23": 230,
        "avg_construction_cost_per_km_cr": 19.2,
        "effective_construction_days_per_year": 240,
        "equipment_utilization_pct": 68.5,
        "source": "Company Operational Data"
    },
    "stress_indicators": {
        "nhai_arbitration_pending_cr": 850,
        "mobilization_advances_outstanding_cr": 420,
        "contract_termination_risk": "High — 1 NHAI project under performance review",
        "subcontractor_payment_delays_days": 45,
        "source": "Company Disclosure; NHAI Project Tracker"
    },
    "development_projections": {
        "projected_km_fy26": 160,
        "projected_km_fy27": 175,
        "projected_revenue_fy26_cr": 2050,
        "projected_revenue_fy27_cr": 2200,
        "capex_plan_fy26_cr": 180,
        "capex_plan_fy27_cr": 200,
        "source": "Company Projections"
    }
}

# PNCR001 already has infra_metrics — sector_kpis extends it with road-specific KPIs
PNCR001_SECTOR_KPIS = {
    "sector_type": "road_construction",
    "highway_mix": {
        "epc_revenue_pct": 67,
        "bot_toll_revenue_pct": 22,
        "ham_annuity_revenue_pct": 11,
        "source": "Company Annual Report FY2025"
    },
    "order_book": {
        "total_order_book_cr": 27680,
        "book_to_bill_ratio": 3.2,
        "epc_orders_cr": 18500,
        "bot_ham_orders_cr": 9180,
        "orders_received_fy25_cr": 12400,
        "executable_order_book_cr": 24500,
        "source": "Company Annual Report FY2025"
    },
    "project_pipeline": [
        {"project_name": "NH-44 4-Laning (Agra-Lucknow)", "length_km": 220, "contract_value_cr": 3850, "completion_pct": 92, "model": "EPC", "client": "NHAI", "target_completion": "Q2 FY2026"},
        {"project_name": "Bundelkhand Expressway Phase-II", "length_km": 145, "contract_value_cr": 2680, "completion_pct": 35, "model": "HAM", "client": "UPEIDA", "target_completion": "Q4 FY2028"},
        {"project_name": "Delhi-Vadodara Greenfield (Pkg-4)", "length_km": 118, "contract_value_cr": 2200, "completion_pct": 68, "model": "EPC", "client": "NHAI", "target_completion": "Q1 FY2027"},
        {"project_name": "Gorakhpur Link Expressway", "length_km": 92, "contract_value_cr": 1580, "completion_pct": 15, "model": "HAM", "client": "UPEIDA", "target_completion": "Q2 FY2029"},
        {"project_name": "NH-30 Widening (Varanasi-Jaunpur)", "length_km": 76, "contract_value_cr": 1250, "completion_pct": 55, "model": "EPC", "client": "MoRTH", "target_completion": "Q3 FY2026"},
    ],
    "execution_metrics": {
        "km_executed_fy25": 385,
        "km_executed_fy24": 340,
        "km_executed_fy23": 295,
        "avg_construction_cost_per_km_cr": 17.5,
        "effective_construction_days_per_year": 255,
        "equipment_utilization_pct": 82.5,
        "physical_progress_pct": 88,
        "cost_overrun_pct": 8.5,
        "time_overrun_pct": 12,
        "structure_cost_pct_of_total": 16,
        "source": "Company Operational Data; NHAI Project Tracker"
    },
    "ham_portfolio": {
        "total_ham_projects": 4,
        "operational_ham_projects": 2,
        "under_construction_ham": 2,
        "total_ham_project_cost_cr": 9180,
        "annuity_income_fy25_cr": 1905,
        "avg_dscr_operational": 1.38,
        "avg_concession_period_years": 18,
        "nhai_grant_received_pct": 88,
        "equity_infusion_complete_pct": 100,
        "source": "Company Annual Report FY2025; Concession Agreements"
    },
    "raw_material_profile": {
        "bitumen_consumption_mt_fy25": 185000,
        "cement_consumption_mt_fy25": 920000,
        "steel_consumption_mt_fy25": 145000,
        "avg_bitumen_price_per_ton_rs": 42500,
        "avg_cement_price_per_bag_rs": 380,
        "source": "Company Procurement Data FY2025"
    },
    "workforce": {
        "direct_employees": 14500,
        "contract_labour": 42000,
        "engineers_technical": 3800,
        "safety_incidents_per_mn_hrs": 0.28,
        "source": "Company HR / ESG Report FY2025"
    },
    "stress_indicators": {
        "nhai_arbitration_pending_cr": 420,
        "mobilization_advances_outstanding_cr": 580,
        "contract_termination_risk": "Low — all projects progressing as per schedule with NHAI early completion bonus track record",
        "subcontractor_payment_delays_days": 22,
        "source": "Company Disclosure; NHAI Project Tracker"
    },
    "development_projections": {
        "projected_km_fy26": 450,
        "projected_km_fy27": 520,
        "projected_revenue_fy26_cr": 10200,
        "projected_revenue_fy27_cr": 12500,
        "projected_annuity_income_fy26_cr": 2100,
        "projected_annuity_income_fy27_cr": 2350,
        "projected_dscr_fy26": 1.35,
        "projected_dscr_fy27": 1.40,
        "capex_plan_fy26_cr": 950,
        "capex_plan_fy27_cr": 1100,
        "new_ham_bids_pipeline_cr": 8500,
        "target_order_book_fy27_cr": 32000,
        "source": "Company Projections; NHAI Award Calendar"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# MANUFACTURING — BMFG001, JSWL001, MFL001, MRF001, MRUT001, REIL001, TSTL001
# ═══════════════════════════════════════════════════════════════════════════════

BMFG001_SECTOR_KPIS = {
    "sector_type": "auto_components",
    "capacity_profile": {
        "installed_capacity_units_pa": 2400000,
        "capacity_utilization_pct_fy25": 78.5,
        "capacity_utilization_pct_fy24": 74.2,
        "capacity_utilization_pct_fy23": 71.0,
        "plants": 3,
        "plant_locations": ["Pune", "Chennai", "Manesar"],
        "source": "Company Annual Report"
    },
    "product_mix": {
        "engine_components_pct": 42,
        "transmission_parts_pct": 28,
        "chassis_parts_pct": 18,
        "electrical_components_pct": 12,
        "source": "Company Product Catalog"
    },
    "customer_concentration": {
        "top_customer_pct": 35,
        "top_3_customers_pct": 68,
        "oem_customers": ["Maruti Suzuki", "Tata Motors", "M&M", "Hyundai"],
        "export_pct": 18,
        "source": "Company Annual Report"
    },
    "raw_material_profile": {
        "steel_cost_pct_of_rm": 55,
        "aluminium_cost_pct_of_rm": 22,
        "rm_to_revenue_pct_fy25": 55.0,
        "rm_to_revenue_pct_fy24": 55.5,
        "inventory_days_rm": 28,
        "source": "Audited Financial Statements"
    },
    "development_projections": {
        "expansion_capex_cr": 85,
        "new_plant_location": "Gujarat (Sanand)",
        "target_capacity_increase_pct": 25,
        "ev_component_order_pipeline_cr": 120,
        "projected_revenue_fy26_cr": 2150,
        "projected_revenue_fy27_cr": 2450,
        "source": "Company Guidance; Board Minutes"
    }
}

TSTL001_SECTOR_KPIS = {
    "sector_type": "steel_manufacturing",
    "capacity_profile": {
        "crude_steel_capacity_mtpa": 34.6,
        "saleable_steel_mtpa_fy25": 31.0,
        "capacity_utilization_pct_fy25": 89.6,
        "capacity_utilization_pct_fy24": 85.2,
        "plants": 8,
        "plant_locations": ["Jamshedpur", "Kalinganagar", "Meramandali", "Angul", "Netherlands", "UK", "Thailand", "Vietnam"],
        "source": "Company Annual Report; World Steel Association"
    },
    "product_mix": {
        "flat_products_pct": 55,
        "long_products_pct": 25,
        "value_added_special_steel_pct": 20,
        "auto_grade_steel_pct": 18,
        "branded_retail_pct": 15,
        "source": "Company Investor Presentation"
    },
    "raw_material_security": {
        "iron_ore_captive_pct": 65,
        "coal_captive_pct": 30,
        "iron_ore_reserves_mn_tons": 720,
        "avg_cost_per_ton_steel_rs": 38500,
        "rm_to_revenue_pct": 62,
        "source": "Company Annual Report; Mining Plan"
    },
    "global_operations": {
        "india_revenue_pct": 68,
        "europe_revenue_pct": 22,
        "asia_ex_india_revenue_pct": 10,
        "employees_global": 73000,
        "source": "Company Annual Report"
    },
    "development_projections": {
        "kalinganagar_expansion_mtpa": 5.0,
        "capex_plan_fy26_cr": 16000,
        "capex_plan_fy27_cr": 14000,
        "target_capacity_mtpa_fy28": 40,
        "projected_revenue_fy26_cr": 68000,
        "projected_revenue_fy27_cr": 75000,
        "source": "Company Guidance; Expansion Plan"
    }
}

REIL001_SECTOR_KPIS = {
    "sector_type": "energy_refining",
    "refining_capacity": {
        "total_refining_capacity_mmtpa": 79.4,
        "throughput_mmtpa_fy25": 72.8,
        "capacity_utilization_pct": 91.7,
        "nelson_complexity_index": 12.8,
        "refineries": 8,
        "refinery_locations": ["Jamnagar-SEZ", "Jamnagar-DTA", "Hazira", "Dahej", "Nagothane"],
        "source": "Company Annual Report; PPAC Data"
    },
    "product_mix": {
        "petrochem_revenue_pct": 38,
        "refining_revenue_pct": 42,
        "retail_pct": 12,
        "telecom_digital_pct": 8,
        "source": "Company Segment Report"
    },
    "retail_network": {
        "fuel_retail_outlets": 17800,
        "jio_subscriber_mn": 489,
        "retail_stores": 18500,
        "new_energy_investments_cr": 75000,
        "source": "Company Annual Report"
    },
    "development_projections": {
        "o2c_expansion_capex_cr": 45000,
        "new_energy_capex_fy26_cr": 22000,
        "projected_revenue_fy26_cr": 580000,
        "projected_revenue_fy27_cr": 625000,
        "target_re_capacity_gw": 20,
        "source": "Company AGM Guidance"
    }
}

JSWL001_SECTOR_KPIS = {
    "sector_type": "steel_manufacturing",
    "capacity_profile": {
        "crude_steel_capacity_mtpa": 37.5,
        "production_mtpa_fy25": 28.8,
        "capacity_utilization_pct_fy25": 76.8,
        "capacity_utilization_pct_fy24": 73.5,
        "plants": 5,
        "plant_locations": ["Vijayanagar", "Dolvi", "Salem", "Raigarh", "Jharsuguda"],
        "source": "Company Annual Report"
    },
    "product_mix": {
        "hr_coils_pct": 40,
        "cr_coils_galvanized_pct": 30,
        "plates_pct": 15,
        "special_steel_pct": 15,
        "source": "Company Investor Deck"
    },
    "cost_position": {
        "avg_cost_per_ton_usd": 425,
        "iron_ore_captive_pct": 55,
        "pellet_capacity_mtpa": 14.5,
        "source": "Company Disclosure; Industry Data"
    },
    "development_projections": {
        "vijayanagar_expansion_mtpa": 5.0,
        "capex_plan_fy26_cr": 20000,
        "capex_plan_fy27_cr": 18000,
        "target_capacity_mtpa_fy28": 42.5,
        "projected_revenue_fy26_cr": 182000,
        "projected_revenue_fy27_cr": 200000,
        "source": "Company Guidance"
    }
}

MFL001_SECTOR_KPIS = {
    "sector_type": "fertilizer_manufacturing",
    "capacity_profile": {
        "urea_capacity_mtpa": 0.77,
        "complex_fertilizer_capacity_mtpa": 0.52,
        "capacity_utilization_urea_pct": 92.5,
        "capacity_utilization_complex_pct": 78.3,
        "plants": 1,
        "plant_location": "Manali, Chennai",
        "source": "Company Annual Report; Dept of Fertilizers"
    },
    "product_mix": {
        "urea_revenue_pct": 48,
        "complex_fertilizer_pct": 32,
        "bio_fertilizer_pct": 5,
        "industrial_chemicals_pct": 15,
        "source": "Company Segment Report"
    },
    "subsidy_profile": {
        "subsidy_income_pct_of_revenue": 65,
        "subsidy_receivable_days": 90,
        "subsidy_receivable_cr": 480,
        "nbs_rate_per_ton_rs": 26800,
        "source": "Dept of Fertilizers; Company Financials"
    },
    "development_projections": {
        "energy_saving_capex_cr": 45,
        "projected_revenue_fy26_cr": 3200,
        "projected_revenue_fy27_cr": 3350,
        "capex_plan_fy26_cr": 55,
        "capex_plan_fy27_cr": 40,
        "source": "Company Board Approval"
    }
}

MRF001_SECTOR_KPIS = {
    "sector_type": "tyre_manufacturing",
    "capacity_profile": {
        "total_tyre_capacity_mn_pa": 65.0,
        "production_mn_fy25": 58.5,
        "capacity_utilization_pct": 90.0,
        "plants": 6,
        "plant_locations": ["Kottayam", "Tiruvottiyur", "Arakkonam", "Goa", "Medak", "Trichy"],
        "source": "Company Annual Report; ATMA Data"
    },
    "product_mix": {
        "truck_bus_radial_pct": 38,
        "passenger_car_radial_pct": 32,
        "two_three_wheeler_pct": 15,
        "off_highway_pct": 8,
        "exports_pct": 7,
        "source": "Company Segment Report"
    },
    "raw_material_profile": {
        "natural_rubber_cost_pct": 35,
        "synthetic_rubber_cost_pct": 18,
        "carbon_black_cost_pct": 12,
        "rm_to_revenue_pct": 60,
        "avg_natural_rubber_price_per_kg_rs": 175,
        "source": "ATMA; Company Procurement Data"
    },
    "market_position": {
        "domestic_market_share_pct": 24,
        "tbr_market_share_pct": 30,
        "pcr_market_share_pct": 22,
        "replacement_market_pct": 65,
        "oem_market_pct": 35,
        "source": "ICRA Industry Report; ATMA"
    },
    "development_projections": {
        "capex_plan_fy26_cr": 2200,
        "capex_plan_fy27_cr": 2000,
        "new_capacity_addition_mn": 8,
        "projected_revenue_fy26_cr": 25000,
        "projected_revenue_fy27_cr": 27500,
        "source": "Company Guidance"
    }
}

MRUT001_SECTOR_KPIS = {
    "sector_type": "automobile_manufacturing",
    "production_profile": {
        "total_production_units_fy25": 2180000,
        "domestic_sales_units_fy25": 1780000,
        "export_units_fy25": 285000,
        "capacity_utilization_pct": 92.4,
        "plants": 3,
        "plant_locations": ["Gurugram", "Manesar", "Gujarat-Hansalpur"],
        "source": "Company Annual Report; SIAM Data"
    },
    "market_position": {
        "domestic_pv_market_share_pct": 42.3,
        "suv_market_share_pct": 25.6,
        "ev_market_share_pct": 2.1,
        "network_outlets": 4800,
        "service_workshops": 5100,
        "source": "SIAM; Company Disclosure"
    },
    "product_mix": {
        "suv_crossover_pct": 42,
        "hatchback_pct": 32,
        "sedan_pct": 12,
        "mpv_pct": 8,
        "cng_pct": 28,
        "ev_pct": 2,
        "avg_selling_price_lakh": 9.8,
        "source": "Company Investor Presentation"
    },
    "development_projections": {
        "kharkhoda_plant_capex_cr": 18000,
        "ev_commitment_cr": 10000,
        "target_production_fy28": 3000000,
        "projected_revenue_fy26_cr": 148000,
        "projected_revenue_fy27_cr": 168000,
        "capex_plan_fy26_cr": 12000,
        "capex_plan_fy27_cr": 15000,
        "source": "Company Annual Report; Capex Plan"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHARMA — CIPL001, DRRD001, SPHR001
# ═══════════════════════════════════════════════════════════════════════════════

CIPL001_SECTOR_KPIS = {
    "sector_type": "pharma_formulations",
    "product_pipeline": {
        "total_anda_filed": 285,
        "anda_approved": 220,
        "pending_anda": 65,
        "nda_filings": 3,
        "peptide_inhalation_pipeline": 12,
        "biosimilar_pipeline": 5,
        "source": "Company Investor Presentation; USFDA"
    },
    "manufacturing": {
        "formulation_plants": 10,
        "api_plants": 4,
        "who_gmp_certified_plants": 12,
        "usfda_approved_plants": 8,
        "capacity_utilization_pct": 72,
        "plant_locations": ["Goa", "Patalganga", "Kurkumbh", "Bengaluru", "Baddi", "Indore"],
        "source": "Company Annual Report"
    },
    "geographic_mix": {
        "india_pct": 40,
        "north_america_pct": 24,
        "africa_pct": 18,
        "europe_pct": 10,
        "row_pct": 8,
        "source": "Company Segment Report"
    },
    "rd_profile": {
        "rd_spend_pct_of_revenue": 5.8,
        "rd_spend_cr_fy25": 1310,
        "rd_employees": 1800,
        "patents_granted": 420,
        "source": "Company R&D Report"
    },
    "regulatory_compliance": {
        "usfda_warning_letters": 0,
        "usfda_observations_fy25": 2,
        "who_prequalified_products": 45,
        "last_usfda_inspection": "Sep 2024",
        "source": "USFDA; WHO"
    },
    "development_projections": {
        "capex_plan_fy26_cr": 1200,
        "capex_plan_fy27_cr": 1400,
        "projected_revenue_fy26_cr": 27500,
        "projected_revenue_fy27_cr": 30500,
        "respiratory_launch_revenue_cr": 850,
        "biosimilar_launch_year": "FY2027",
        "source": "Company Guidance"
    }
}

DRRD001_SECTOR_KPIS = {
    "sector_type": "pharma_formulations",
    "product_pipeline": {
        "total_anda_filed": 340,
        "anda_approved": 275,
        "pending_anda": 65,
        "complex_generic_filings": 28,
        "biosimilar_pipeline": 9,
        "source": "Company Investor Presentation; USFDA"
    },
    "manufacturing": {
        "formulation_plants": 14,
        "api_plants": 8,
        "total_manufacturing_sites": 24,
        "usfda_approved_plants": 11,
        "capacity_utilization_pct": 74,
        "plant_locations": ["Hyderabad", "Vizag", "Bachupally", "CTO Hyderabad", "Mexico", "UK", "USA"],
        "source": "Company Annual Report"
    },
    "geographic_mix": {
        "north_america_pct": 45,
        "india_pct": 20,
        "europe_pct": 15,
        "emerging_markets_pct": 20,
        "source": "Company Segment Report"
    },
    "rd_profile": {
        "rd_spend_pct_of_revenue": 12.5,
        "rd_spend_cr_fy25": 3400,
        "rd_employees": 3200,
        "patents_granted": 680,
        "source": "Company R&D Report"
    },
    "regulatory_compliance": {
        "usfda_warning_letters": 0,
        "usfda_observations_fy25": 1,
        "last_usfda_inspection": "Nov 2024",
        "ema_inspections_passed": 4,
        "source": "USFDA; EMA"
    },
    "development_projections": {
        "capex_plan_fy26_cr": 2200,
        "capex_plan_fy27_cr": 2500,
        "projected_revenue_fy26_cr": 30000,
        "projected_revenue_fy27_cr": 34000,
        "biosimilar_revenue_target_cr": 4500,
        "source": "Company Guidance"
    }
}

SPHR001_SECTOR_KPIS = {
    "sector_type": "pharma_api_formulations",
    "product_portfolio": {
        "total_products": 85,
        "anda_filed": 18,
        "anda_approved": 12,
        "dmf_filed": 35,
        "active_dossiers": 45,
        "source": "Company Records"
    },
    "manufacturing": {
        "formulation_plants": 2,
        "api_plants": 1,
        "who_gmp_certified": True,
        "usfda_approved": False,
        "capacity_utilization_pct": 68,
        "plant_locations": ["Ahmedabad", "Ankleshwar"],
        "source": "Company Annual Report"
    },
    "geographic_mix": {
        "india_pct": 55,
        "africa_pct": 25,
        "asia_ex_india_pct": 12,
        "latam_pct": 8,
        "source": "Company Export Data"
    },
    "rd_profile": {
        "rd_spend_pct_of_revenue": 4.2,
        "rd_spend_cr_fy25": 17.6,
        "patents_filed": 8,
        "source": "Company R&D Report"
    },
    "group_risk_factors": {
        "group_entity_fda_warning": "Sunrise Biotech — FDA Warning Letter (Oct 2024)",
        "related_party_transactions_cr": 42,
        "promoter_holding_pct": 85,
        "group_entities_count": 4,
        "source": "Company Disclosure; MCA Filings"
    },
    "development_projections": {
        "capex_plan_fy26_cr": 28,
        "capex_plan_fy27_cr": 35,
        "projected_revenue_fy26_cr": 465,
        "projected_revenue_fy27_cr": 510,
        "usfda_filing_target": "FY2027",
        "source": "Company Projections"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# HEALTHCARE — APOL001
# ═══════════════════════════════════════════════════════════════════════════════

APOL001_SECTOR_KPIS = {
    "sector_type": "hospitals_healthcare",
    "hospital_network": {
        "total_hospitals": 73,
        "owned_hospitals": 42,
        "managed_hospitals": 31,
        "total_beds": 10122,
        "operational_beds": 8850,
        "icu_beds": 2200,
        "avg_occupancy_pct_fy25": 68.5,
        "avg_occupancy_pct_fy24": 65.2,
        "avg_occupancy_pct_fy23": 62.8,
        "source": "Company Annual Report"
    },
    "revenue_metrics": {
        "arpob_rs_fy25": 48500,
        "arpob_rs_fy24": 45200,
        "arpob_rs_fy23": 42800,
        "alos_days": 3.8,
        "payor_mix_insurance_pct": 45,
        "payor_mix_self_pay_pct": 38,
        "payor_mix_govt_pct": 17,
        "source": "Company Investor Presentation"
    },
    "pharmacy_network": {
        "apollo_pharmacy_stores": 5800,
        "pharmacy_revenue_cr_fy25": 7200,
        "pharmacy_ebitda_margin_pct": 4.2,
        "online_pharmacy_pct": 15,
        "source": "Company Segment Report"
    },
    "digital_health": {
        "apollo_247_users_mn": 42,
        "teleconsultation_mn_fy25": 8.5,
        "apollo_healthco_revenue_cr": 1200,
        "source": "Company Digital Health Report"
    },
    "clinical_excellence": {
        "organ_transplants_fy25": 1850,
        "cardiac_surgeries_fy25": 12500,
        "international_patients_fy25": 45000,
        "nabh_accredited_hospitals": 42,
        "jci_accredited": 5,
        "source": "Company Clinical Report; NABH"
    },
    "development_projections": {
        "new_beds_addition_fy26": 1200,
        "new_beds_addition_fy27": 1500,
        "capex_plan_fy26_cr": 2800,
        "capex_plan_fy27_cr": 3200,
        "projected_revenue_fy26_cr": 22000,
        "projected_revenue_fy27_cr": 25500,
        "target_occupancy_fy28_pct": 75,
        "source": "Company Guidance; Hospital Expansion Plan"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# IT SERVICES — INFY001
# ═══════════════════════════════════════════════════════════════════════════════

INFY001_SECTOR_KPIS = {
    "sector_type": "it_services",
    "deal_pipeline": {
        "total_deal_value_bn_usd_fy25": 17.2,
        "large_deal_wins_fy25_bn_usd": 11.5,
        "large_deal_count_fy25": 32,
        "new_deals_pct": 52,
        "renewal_deals_pct": 48,
        "avg_deal_duration_years": 3.8,
        "source": "Company Investor Presentation"
    },
    "operational_metrics": {
        "total_employees": 317240,
        "utilization_rate_pct": 82.5,
        "utilization_excl_trainees_pct": 85.8,
        "attrition_rate_ltm_pct": 12.8,
        "revenue_per_employee_usd_k": 58.5,
        "onsite_pct": 24.5,
        "offshore_pct": 75.5,
        "freshers_hired_fy25": 15000,
        "source": "Company Quarterly Results; HR Report"
    },
    "service_mix": {
        "digital_revenue_pct": 64.2,
        "cloud_revenue_pct": 18,
        "ai_ml_revenue_pct": 8,
        "consulting_pct": 12,
        "core_it_pct": 35.8,
        "source": "Company Segment Report"
    },
    "geographic_mix": {
        "north_america_pct": 60.5,
        "europe_pct": 25.8,
        "india_pct": 3.2,
        "row_pct": 10.5,
        "source": "Company Segment Report"
    },
    "client_metrics": {
        "total_clients": 1850,
        "usd_100m_plus_clients": 42,
        "usd_50m_plus_clients": 85,
        "client_concentration_top5_pct": 14.2,
        "source": "Company Annual Report"
    },
    "development_projections": {
        "revenue_guidance_growth_pct": "4-7%",
        "ebit_margin_guidance_pct": "20-22%",
        "projected_revenue_fy26_cr": 168000,
        "projected_revenue_fy27_cr": 178000,
        "capex_plan_fy26_cr": 3500,
        "capex_plan_fy27_cr": 3800,
        "ai_services_target_revenue_pct": 15,
        "source": "Company Guidance; Analyst Day"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# NBFC / BANKING — BJFN001, YESB001
# ═══════════════════════════════════════════════════════════════════════════════

BJFN001_SECTOR_KPIS = {
    "sector_type": "nbfc",
    "aum_profile": {
        "total_aum_cr": 330000,
        "aum_growth_yoy_pct": 28.5,
        "retail_aum_pct": 62,
        "sme_aum_pct": 22,
        "commercial_aum_pct": 16,
        "source": "Company Quarterly Results"
    },
    "asset_quality": {
        "gnpa_pct_fy25": 0.95,
        "gnpa_pct_fy24": 1.12,
        "gnpa_pct_fy23": 1.28,
        "nnpa_pct_fy25": 0.38,
        "pcr_pct": 60,
        "sma1_pct": 0.45,
        "sma2_pct": 0.18,
        "source": "Company Quarterly Results; RBI Data"
    },
    "profitability": {
        "nim_pct_fy25": 10.2,
        "nim_pct_fy24": 9.8,
        "cost_to_income_pct": 33.5,
        "roe_pct": 22.8,
        "roa_pct": 4.2,
        "source": "Company Financial Results"
    },
    "capital_adequacy": {
        "car_pct": 24.6,
        "tier1_pct": 22.8,
        "leverage_ratio": 6.8,
        "source": "Company Quarterly Results; RBI Data"
    },
    "disbursement_metrics": {
        "total_disbursements_cr_fy25": 285000,
        "disbursement_growth_yoy_pct": 26,
        "digital_disbursement_pct": 45,
        "avg_ticket_size_lakh": 12.5,
        "source": "Company Investor Presentation"
    },
    "development_projections": {
        "aum_target_fy27_cr": 500000,
        "branch_expansion_fy26": 180,
        "projected_revenue_fy26_cr": 62000,
        "projected_revenue_fy27_cr": 78000,
        "capex_plan_fy26_cr": 2200,
        "capex_plan_fy27_cr": 2500,
        "source": "Company Guidance"
    }
}

YESB001_SECTOR_KPIS = {
    "sector_type": "banking",
    "balance_sheet_profile": {
        "total_deposits_cr": 228000,
        "casa_ratio_pct": 30.2,
        "retail_deposits_pct": 55,
        "total_advances_cr": 215000,
        "retail_advances_pct": 48,
        "corporate_advances_pct": 35,
        "sme_advances_pct": 17,
        "source": "Company Quarterly Results; RBI Data"
    },
    "asset_quality": {
        "gnpa_pct_fy25": 2.20,
        "gnpa_pct_fy24": 3.80,
        "gnpa_pct_fy23": 5.20,
        "nnpa_pct_fy25": 0.85,
        "pcr_pct": 72,
        "slippage_ratio_pct": 1.80,
        "restructured_book_pct": 2.5,
        "source": "Company Results; RBI Supervisory Data"
    },
    "profitability": {
        "nim_pct_fy25": 2.45,
        "nim_pct_fy24": 2.28,
        "cost_to_income_pct": 68.5,
        "roe_pct": 3.2,
        "roa_pct": 0.22,
        "source": "Company Financial Results"
    },
    "capital_adequacy": {
        "car_pct": 16.8,
        "cet1_pct": 12.5,
        "tier2_pct": 4.3,
        "source": "Company Quarterly Results; RBI Data"
    },
    "governance_concerns": {
        "rbi_penalties_fy25_cr": 2.0,
        "former_md_conviction": "Rana Kapoor — money laundering conviction (₹4,300 Cr fraud)",
        "fraud_provisions_cr": 850,
        "board_reconstitution_date": "Mar 2020",
        "source": "RBI Orders; Court Records; Company Disclosure"
    },
    "development_projections": {
        "credit_growth_target_pct": 15,
        "casa_target_pct": 35,
        "projected_advances_fy26_cr": 247000,
        "projected_revenue_fy26_cr": 28500,
        "projected_revenue_fy27_cr": 32000,
        "roe_target_fy27_pct": 8,
        "source": "Company Investor Day; Management Commentary"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# REAL ESTATE — DLFR001
# ═══════════════════════════════════════════════════════════════════════════════

DLFR001_SECTOR_KPIS = {
    "sector_type": "real_estate_development",
    "development_portfolio": {
        "total_developable_area_msf": 215,
        "completed_area_msf": 145,
        "ongoing_projects_msf": 38,
        "planned_area_msf": 32,
        "luxury_residential_pct": 35,
        "commercial_office_pct": 40,
        "retail_pct": 15,
        "plotted_development_pct": 10,
        "source": "Company Annual Report"
    },
    "sales_performance": {
        "new_bookings_cr_fy25": 15500,
        "new_bookings_cr_fy24": 14800,
        "new_bookings_cr_fy23": 8000,
        "collections_cr_fy25": 12800,
        "unsold_inventory_cr": 28000,
        "avg_realization_per_sqft_rs": 12500,
        "source": "Company Quarterly Results; RERA Data"
    },
    "rental_portfolio": {
        "total_leasable_area_msf": 42.5,
        "leased_area_msf": 38.2,
        "occupancy_pct": 89.8,
        "rental_income_cr_fy25": 6200,
        "avg_rental_per_sqft_month_rs": 125,
        "source": "Company Annual Report; Property Records"
    },
    "land_bank": {
        "total_land_bank_acres": 160,
        "land_cost_cr": 4500,
        "market_value_cr": 22000,
        "licensed_area_msf": 85,
        "source": "Company Disclosure; Circle Rate Data"
    },
    "debt_profile": {
        "net_debt_cr": 4200,
        "net_debt_equity": 0.45,
        "avg_cost_of_debt_pct": 8.2,
        "upcoming_maturities_fy26_cr": 1800,
        "source": "Company Financial Statements"
    },
    "development_projections": {
        "new_launches_msf_fy26": 12,
        "capex_plan_fy26_cr": 4500,
        "capex_plan_fy27_cr": 5000,
        "projected_revenue_fy26_cr": 7500,
        "projected_revenue_fy27_cr": 8800,
        "presales_target_fy26_cr": 17000,
        "source": "Company Guidance; Launch Pipeline"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# HOSPITALITY — IHCL001
# ═══════════════════════════════════════════════════════════════════════════════

IHCL001_SECTOR_KPIS = {
    "sector_type": "hospitality",
    "hotel_portfolio": {
        "total_hotels": 255,
        "total_rooms": 24600,
        "owned_leased_hotels": 85,
        "managed_hotels": 120,
        "franchise_hotels": 50,
        "brands": ["Taj", "SeleQtions", "Vivanta", "Ginger", "amã Stays"],
        "countries": 18,
        "source": "Company Annual Report"
    },
    "operational_metrics": {
        "avg_occupancy_pct_fy25": 72.8,
        "avg_occupancy_pct_fy24": 69.5,
        "avg_occupancy_pct_fy23": 66.2,
        "arr_rs_fy25": 12800,
        "arr_rs_fy24": 11500,
        "arr_rs_fy23": 10200,
        "revpar_rs_fy25": 9320,
        "revpar_rs_fy24": 7990,
        "revpar_rs_fy23": 6750,
        "source": "Company Investor Presentation; HVS Data"
    },
    "revenue_mix": {
        "rooms_pct": 52,
        "food_beverage_pct": 30,
        "management_fees_pct": 8,
        "amã_stays_pct": 5,
        "other_pct": 5,
        "source": "Company Segment Report"
    },
    "pipeline": {
        "rooms_under_development": 5800,
        "new_hotel_signings_fy25": 42,
        "international_pipeline_rooms": 1200,
        "ginger_expansion_rooms": 2800,
        "source": "Company Pipeline Report"
    },
    "development_projections": {
        "target_rooms_fy28": 35000,
        "capex_plan_fy26_cr": 1800,
        "capex_plan_fy27_cr": 2200,
        "projected_revenue_fy26_cr": 8200,
        "projected_revenue_fy27_cr": 9500,
        "target_revpar_fy27_rs": 11000,
        "source": "Company Guidance; Expansion Plan"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# LOGISTICS — OLOG001
# ═══════════════════════════════════════════════════════════════════════════════

OLOG001_SECTOR_KPIS = {
    "sector_type": "logistics_3pl",
    "fleet_profile": {
        "total_vehicles": 2200,
        "owned_vehicles": 850,
        "leased_vehicles": 1350,
        "avg_fleet_age_years": 4.2,
        "fleet_utilization_pct_fy25": 78.5,
        "fleet_utilization_pct_fy24": 75.2,
        "fleet_utilization_pct_fy23": 72.0,
        "source": "Company Operational Data"
    },
    "warehousing": {
        "total_warehouse_area_sqft": 2800000,
        "owned_warehouse_pct": 25,
        "leased_warehouse_pct": 75,
        "warehouse_locations": 28,
        "cold_storage_capacity_mt": 15000,
        "occupancy_pct": 82,
        "source": "Company Annual Report"
    },
    "route_network": {
        "total_routes": 450,
        "express_routes": 120,
        "ptl_routes": 280,
        "ftl_routes": 50,
        "pin_codes_served": 18500,
        "avg_transit_days_metro": 1.5,
        "source": "Company Network Report"
    },
    "cost_structure": {
        "fuel_cost_pct_revenue": 32,
        "driver_cost_pct_revenue": 18,
        "toll_cost_pct_revenue": 8,
        "avg_fuel_cost_per_km_rs": 12.5,
        "avg_revenue_per_ton_km_rs": 2.8,
        "source": "Company Financial Data"
    },
    "technology": {
        "gps_tracked_fleet_pct": 95,
        "digital_pod_pct": 78,
        "route_optimization_ai": True,
        "customer_app_users": 28000,
        "source": "Company Technology Report"
    },
    "development_projections": {
        "fleet_expansion_vehicles": 400,
        "new_warehouse_sqft": 800000,
        "capex_plan_fy26_cr": 65,
        "capex_plan_fy27_cr": 80,
        "projected_revenue_fy26_cr": 640,
        "projected_revenue_fy27_cr": 720,
        "ev_fleet_target_pct": 10,
        "source": "Company Growth Plan"
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# TRADING / RETAIL — TITN001
# ═══════════════════════════════════════════════════════════════════════════════

TITN001_SECTOR_KPIS = {
    "sector_type": "luxury_retail",
    "retail_network": {
        "total_stores": 2850,
        "tanishq_stores": 520,
        "titan_eye_stores": 780,
        "watches_stores": 1200,
        "caratlane_stores": 250,
        "other_stores": 100,
        "tier1_city_pct": 35,
        "tier2_city_pct": 40,
        "tier3_city_pct": 25,
        "source": "Company Annual Report"
    },
    "segment_performance": {
        "jewellery_revenue_pct": 88,
        "watches_revenue_pct": 7,
        "eyecare_revenue_pct": 3,
        "other_pct": 2,
        "jewellery_ebit_margin_pct": 13.5,
        "watches_ebit_margin_pct": 8.2,
        "sssg_jewellery_pct": 18.5,
        "sssg_watches_pct": 12.0,
        "source": "Company Segment Report"
    },
    "gold_profile": {
        "gold_inventory_cr": 12500,
        "gold_hedging_coverage_pct": 75,
        "avg_gold_purchase_price_per_gm_rs": 6200,
        "gold_on_lease_cr": 8500,
        "making_charge_pct": 14,
        "source": "Company Annual Report; MCX Data"
    },
    "digital_presence": {
        "online_revenue_pct": 12,
        "caratlane_online_pct": 35,
        "omnichannel_stores": 1800,
        "loyalty_program_members_mn": 22,
        "source": "Company Digital Report"
    },
    "development_projections": {
        "new_stores_fy26": 280,
        "tanishq_target_stores_fy28": 750,
        "capex_plan_fy26_cr": 1800,
        "capex_plan_fy27_cr": 2000,
        "projected_revenue_fy26_cr": 58000,
        "projected_revenue_fy27_cr": 66000,
        "international_expansion_stores": 15,
        "source": "Company Guidance; Expansion Plan"
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER REGISTRY — maps entity_id → sector_kpis dict
# ═══════════════════════════════════════════════════════════════════════════════

SECTOR_KPIS = {
    # Infrastructure
    "ADPT001": ADPT001_SECTOR_KPIS,
    "NTPC001": NTPC001_SECTOR_KPIS,
    "PINF001": PINF001_SECTOR_KPIS,
    "PNCR001": PNCR001_SECTOR_KPIS,
    # Manufacturing
    "BMFG001": BMFG001_SECTOR_KPIS,
    "TSTL001": TSTL001_SECTOR_KPIS,
    "REIL001": REIL001_SECTOR_KPIS,
    "JSWL001": JSWL001_SECTOR_KPIS,
    "MFL001":  MFL001_SECTOR_KPIS,
    "MRF001":  MRF001_SECTOR_KPIS,
    "MRUT001": MRUT001_SECTOR_KPIS,
    # Pharma
    "CIPL001": CIPL001_SECTOR_KPIS,
    "DRRD001": DRRD001_SECTOR_KPIS,
    "SPHR001": SPHR001_SECTOR_KPIS,
    # Healthcare
    "APOL001": APOL001_SECTOR_KPIS,
    # IT Services
    "INFY001": INFY001_SECTOR_KPIS,
    # NBFC / Banking
    "BJFN001": BJFN001_SECTOR_KPIS,
    "YESB001": YESB001_SECTOR_KPIS,
    # Real Estate
    "DLFR001": DLFR001_SECTOR_KPIS,
    # Hospitality
    "IHCL001": IHCL001_SECTOR_KPIS,
    # Logistics
    "OLOG001": OLOG001_SECTOR_KPIS,
    # Trading / Retail
    "TITN001": TITN001_SECTOR_KPIS,
}
