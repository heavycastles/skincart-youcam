"""One real YouCam call pair (skin analysis + lip VTO) against a selfie. Costs units - run once with a key.

    YOUCAM_API_KEY=... python scripts/live_smoke.py path/to/selfie.jpg
"""

import json
import sys

from app.recommend import get_product
from app.youcam import YouCamClient

client = YouCamClient()
if client.mock:
    sys.exit("set YOUCAM_API_KEY first")
image = open(sys.argv[1], "rb").read()  # noqa: SIM115
scores = client.skin_analysis(image=image)
print(json.dumps([s.__dict__ for s in scores], indent=2))
print("VTO:", client.makeup_vto([get_product("SC-LIP-10")["vto"]], image=image))
