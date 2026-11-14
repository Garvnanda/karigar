# Nonilion setup: import Sakhi and Karigar

Prerequisite: the Karigar service is deployed on Render and the worker is running on the laptop (docs/testing.md "Deploy").
You need: the service URL (e.g. `https://karigar.onrender.com`) and the `KARIGAR_API_KEY` value set in Render.

## Sakhi (counter)
1. Open the Nonilion room → agent panel → **IMPORT** → **Other**.
2. Name: `Sakhi`. Avatar: any.
3. API key: the `KARIGAR_API_KEY` value.
4. Where is it?: `https://<your-service>.onrender.com/sakhi/v1`
5. Its instructions: paste the whole of `nonilion/sakhi.md`.
6. Click **Test the key**. It must pass. If it fails, check the service is awake (`https://<your-service>.onrender.com/` returns ok) and the key has no spaces.
7. Save.

## Karigar (workshop)
Same steps, with:
- Name: `Karigar`
- Where is it?: `https://<your-service>.onrender.com/karigar/v1`
- Its instructions: `nonilion/karigar.md`

## Check
In the room, send: `Nani ka purana 18.4g 22K kangan hai, naya 22K beaded kada banana hai, size 2-6`.
Expected: progress lines, then 3 designs with weight ± tolerance, total ₹ and links. If it says "still working", send any message after a minute.
