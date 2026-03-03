#!/usr/bin/env python3
"""runner.py — JSON-in/JSON-out wrapper for the FaIR simple climate model.

TO RUN:
  From inside the repo root:
    python runner.py < input.json

  Or with a file:
    python runner.py input.json

INPUT JSON keys:
  start_year               int    first timebound year             (default: 2000)
  end_year                 int    last timebound year              (default: 2050)
  step                     int    timestep in years                (default: 1)
  scenarios                list   scenario labels                  (default: ["abrupt", "ramp"])
  configs                  list   config labels                    (default: ["high", "central", "low"])
  ghg_method               str    GHG forcing method               (default: "myhre1998")
  species_properties_file  str    path to species_configs_properties CSV
  emissions_file           str    path to emissions CSV
  concentration_file       str    path to concentration CSV
  forcing_file             str    path to forcing CSV
  ensemble_file            str    path to configs_ensemble CSV
  initial_co2_ppm          float  initial CO2 concentration (ppm)  (default: 278.3)

OUTPUT JSON keys:
  timebounds      list  year values at each timebound
  scenarios       list  scenario labels
  configs         list  config labels
  temperature_K   dict  surface (layer=0) temperature anomaly (K)   {scenario: {config: [...]}}
  co2_ppm         dict  CO2 concentration (ppm)                     {scenario: {config: [...]}}
  forcing_sum_Wm2 dict  total effective radiative forcing (W m-2)   {scenario: {config: [...]}}
"""


"""
What Claude had me do:
python3.12 -m venv .venv --without-pip
source .venv/bin/activate
curl https://bootstrap.pypa.io/get-pip.py | python
pip install -e .

source .venv/bin/activate
echo '{}' | python runner.py

# That works because there are defaults for all the necessary values,
# so you can pass in '{}' as the input, and it'll use the defaults


"""

import argparse
import json
import os
import sys

try:
    from fair import FAIR
    from fair.interface import initialise
    from fair.io import read_properties
except ModuleNotFoundError as exc:
    missing = getattr(exc, "name", None) or str(exc)
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    msg_lines = [
        "Failed to import FaIR dependencies.",
        f"Missing module: {missing}",
        f"Python: {pyver}",
        "",
        "Fix:",
        "- Create/activate a venv, then install FaIR:",
        "    python -m venv .venv",
        "    source .venv/bin/activate",
        "    python -m pip install -U pip",
        "    python -m pip install -e .",
        "",
        "Then run:",
        "    python runner.py < input.json",
    ]
    print("\n".join(msg_lines), file=sys.stderr)
    raise

# Paths to bundled example data files (relative to this file)
_EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "examples", "data")
_DEFAULT_SPECIES_PROPS = os.path.join(
    _EXAMPLES_DIR, "importing-data", "species_configs_properties.csv"
)
_DEFAULT_EMISSIONS = os.path.join(
    _EXAMPLES_DIR, "basic_run_example", "emissions.csv"
)
_DEFAULT_CONCENTRATION = os.path.join(
    _EXAMPLES_DIR, "basic_run_example", "concentration.csv"
)
_DEFAULT_FORCING = os.path.join(
    _EXAMPLES_DIR, "basic_run_example", "forcing.csv"
)
_DEFAULT_ENSEMBLE = os.path.join(
    _EXAMPLES_DIR, "basic_run_example", "configs_ensemble.csv"
)


def _to_nested_dict(da, scenarios, configs, extra_sel):
    """Slice an xarray DataArray and convert to {scenario: {config: list}}."""
    result = {}
    for scenario in scenarios:
        result[scenario] = {}
        for config in configs:
            selection = dict(scenario=scenario, config=config, **extra_sel)
            result[scenario][config] = da.loc[selection].values.tolist()
    return result


def run(params: dict) -> dict:
    # --- 1. Create FaIR instance ---
    f = FAIR()

    # --- 2. Define time horizon ---
    f.define_time(
        params.get("start_year", 2000),
        params.get("end_year", 2050),
        params.get("step", 1),
    )

    # --- 3. Define scenarios ---
    scenarios = params.get("scenarios", ["abrupt", "ramp"])
    f.define_scenarios(scenarios)

    # --- 4. Define configs ---
    configs = params.get("configs", ["high", "central", "low"])
    f.define_configs(configs)

    # --- 5. Define species and their properties ---
    species_props_file = params.get("species_properties_file", _DEFAULT_SPECIES_PROPS)
    species, properties = read_properties(species_props_file)
    f.define_species(species, properties)

    # --- 6. Modify run options ---
    f.ghg_method = params.get("ghg_method", "myhre1998")

    # --- 7. Allocate data arrays ---
    f.allocate()

    # --- 8a. Fill emissions, concentrations, and forcing from CSV files ---
    f.fill_from_csv(
        emissions_file=params.get("emissions_file", _DEFAULT_EMISSIONS),
        concentration_file=params.get("concentration_file", _DEFAULT_CONCENTRATION),
        forcing_file=params.get("forcing_file", _DEFAULT_FORCING),
    )

    # Initialise state variables
    initialise(f.concentration, params.get("initial_co2_ppm", 278.3), specie="CO2")
    initialise(f.forcing, 0)
    initialise(f.temperature, 0)
    initialise(f.cumulative_emissions, 0)
    initialise(f.airborne_emissions, 0)
    initialise(f.ocean_heat_content_change, 0)

    # --- 8b. Fill species configs and override with ensemble parameters ---
    f.fill_species_configs(species_props_file)
    f.override_defaults(params.get("ensemble_file", _DEFAULT_ENSEMBLE))

    # --- 9. Run the model ---
    f.run()

    # --- 10. Collect and return results ---
    return {
        "timebounds": f.timebounds.tolist(),
        "scenarios": list(scenarios),
        "configs": list(configs),
        # Surface (layer=0) temperature anomaly in K
        "temperature_K": _to_nested_dict(
            f.temperature, scenarios, configs, {"layer": 0}
        ),
        # CO2 concentration in ppm
        "co2_ppm": _to_nested_dict(
            f.concentration, scenarios, configs, {"specie": "CO2"}
        ),
        # Total effective radiative forcing in W m-2
        "forcing_sum_Wm2": _to_nested_dict(
            f.forcing_sum, scenarios, configs, {}
        ),
    }


def _load_input_json() -> dict:
    parser = argparse.ArgumentParser(
        description="FaIR runner: read climate scenario inputs as JSON and emit JSON results."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to input JSON file, or '-' to read from stdin (default).",
    )
    args = parser.parse_args()

    if args.input == "-":
        return json.load(sys.stdin)

    with open(args.input, "r", encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    input_data = _load_input_json()
    output_data = run(input_data)
    json.dump(output_data, sys.stdout, indent=2)
    print()  # trailing newline
