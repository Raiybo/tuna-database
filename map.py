#!/usr/bin/env python3
"""
map.py - Visual map overview of where the fish are, off Marina Dbaye.

Builds map.html (interactive Leaflet map, opens in a browser tab) showing:
  * the satellite SST field (coloured dots) so you SEE the temperature break
  * today's casting spots (green)
  * your own GPS marks (gold)
  * the offshore bluefin front zones (red)

    python map.py
"""

import json
import os
import webbrowser

import tuna
import bluefin

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    data = tuna.gather(quiet=True)
    today = data["days"][0]
    home = data["home"]

    # Wide satellite SST field for the temperature-break picture.
    try:
        sdate, wide_sst = bluefin.fetch("CRW_sst_v3_1", "analysed_sst", False)
    except Exception:
        sdate, wide_sst = None, []
        sat = today.get("sat", {}).get("sst")
        if sat:
            sdate = sat.get("date")
            wide_sst = [{"lat": p["lat"], "lon": p["lon"], "val": p["val"]} for p in sat["grid"]]

    sst_pts = [[round(p["lat"], 4), round(p["lon"], 4), round(p["val"], 2)] for p in wide_sst]
    temps = [p[2] for p in sst_pts] or [22, 24]
    tmin, tmax = min(temps), max(temps)

    spots = []

    # casting spots (today's best cells)
    for c in today["cells"][:6]:
        if c.get("sst") is None:
            continue
        spots.append({
            "lat": c["lat"], "lon": c["lon"], "kind": "cast", "score": c["score"],
            "label": f"Casting spot · {c['score']}",
            "detail": f"SST {c['sst']:.1f}&deg;C · current {c['cur']:.1f} km/h · "
                      f"{c['dist_nm']} nm {tuna.compass(c['brg'])}",
        })

    # your own marks
    for s in today["your_spots"]:
        spots.append({
            "lat": s["lat"], "lon": s["lon"], "kind": "mark", "score": s["score"],
            "label": f"{s['name']} · {s['score']}",
            "detail": (f"SST {s['sst']:.1f}&deg;C · " if s.get("sst") is not None else "")
                      + f"{s['dist_nm']} nm {tuna.compass(s['brg'])}",
        })

    # offshore bluefin zones
    bf = os.path.join(HERE, "bluefin.json")
    if os.path.exists(bf):
        with open(bf, encoding="utf-8") as f:
            for z in json.load(f).get("zones", []):
                chs = f" · chl {z['chla']:.2f}" if z.get("chla") is not None else ""
                spots.append({
                    "lat": z["lat"], "lon": z["lon"], "kind": "bluefin", "score": round(z["score"]),
                    "label": f"Bluefin zone · break {z['grad']:.2f}&deg;C",
                    "detail": f"SST {z['val']:.1f}&deg;C · {z['dist']:.0f} nm "
                              f"{tuna.compass(z['brg'])}{chs}",
                })

    payload = {
        "home": {"lat": home["lat"], "lon": home["lon"], "name": home["name"]},
        "tmin": tmin, "tmax": tmax, "sst": sst_pts, "spots": spots,
        "date": str(today["date"]), "sstdate": str(sdate)[:10],
        "score": today["score"], "verdict": today["verdict"],
    }

    html = TEMPLATE.replace("/*__DATA__*/", json.dumps(payload))
    out = os.path.join(HERE, "map.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Map written: {out}")
    print(f"  {len(sst_pts)} SST points, {len(spots)} marked spots")
    webbrowser.open("file:///" + out.replace("\\", "/"))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tuna map · Dbaye</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{margin:0;height:100%;background:#0a1622;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
  #map{position:absolute;top:0;bottom:0;left:0;right:0}
  .hud{position:absolute;z-index:1000;top:10px;left:10px;background:rgba(10,22,34,.92);color:#e8f0f7;
       padding:10px 13px;border-radius:12px;font-size:13px;max-width:240px;box-shadow:0 2px 12px rgba(0,0,0,.5)}
  .hud h1{font-size:15px;margin:0 0 4px}
  .hud .s{font-size:11px;color:#7d97ad}
  .legend{position:absolute;z-index:1000;bottom:14px;left:10px;background:rgba(10,22,34,.92);color:#e8f0f7;
          padding:9px 12px;border-radius:12px;font-size:12px;line-height:1.7}
  .dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:middle}
  .bar{height:9px;width:150px;border-radius:5px;margin:4px 0 2px;
       background:linear-gradient(90deg,hsl(240,80%,55%),hsl(120,80%,50%),hsl(0,80%,55%))}
  .leaflet-popup-content{font-size:13px}
  .leaflet-popup-content b{font-size:14px}
</style></head><body>
<div id="map"></div>
<div class="hud"><h1>🎣 Where the fish are</h1>
  <div id="hudtxt" class="s"></div></div>
<div class="legend" id="legend"></div>
<script>
const D = /*__DATA__*/;

const map = L.map('map', {zoomControl:true});
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {attribution:'&copy; OpenStreetMap &copy; CARTO', maxZoom:19}).addTo(map);

document.getElementById('hudtxt').innerHTML =
  D.date + ' · score ' + D.score + '/100<br>' + D.verdict +
  '<br>SST field: ' + D.sstdate;

// --- temperature field (the break) ---
function tcolor(v){
  let t = (D.tmax>D.tmin) ? (v-D.tmin)/(D.tmax-D.tmin) : 0.5;
  let hue = 240 - 240*t;              // blue(cold) -> red(warm)
  return 'hsl('+hue+',80%,55%)';
}
const sstLayer = L.layerGroup();
D.sst.forEach(p=>{
  L.circleMarker([p[0],p[1]], {radius:5, stroke:false, fillColor:tcolor(p[2]),
    fillOpacity:0.55}).bindTooltip(p[2].toFixed(1)+'°C').addTo(sstLayer);
});
sstLayer.addTo(map);

// --- home port ---
L.marker([D.home.lat, D.home.lon]).addTo(map)
  .bindPopup('<b>'+D.home.name+'</b><br>Home port');

// --- fish spots ---
const KIND = {
  cast:    {color:'#2ecc71', r:8,  name:'Casting spot (bonito/skipjack)'},
  mark:    {color:'#f1c40f', r:8,  name:'Your GPS mark'},
  bluefin: {color:'#e74c3c', r:10, name:'Bluefin front zone (offshore)'}
};
const groups = {cast:L.layerGroup(), mark:L.layerGroup(), bluefin:L.layerGroup()};
const bounds = [[D.home.lat, D.home.lon]];
D.spots.forEach(s=>{
  const k = KIND[s.kind];
  L.circleMarker([s.lat,s.lon], {radius:k.r, color:'#0a1622', weight:1.5,
     fillColor:k.color, fillOpacity:0.95})
   .bindPopup('<b>'+s.label+'</b><br>'+s.detail+'<br><span style="color:#888">'+
       s.lat.toFixed(4)+', '+s.lon.toFixed(4)+'</span>')
   .addTo(groups[s.kind]);
  bounds.push([s.lat,s.lon]);
});
Object.values(groups).forEach(g=>g.addTo(map));

map.fitBounds(bounds, {padding:[50,50]});

L.control.layers(null, {
  'Temperature field': sstLayer,
  'Casting spots': groups.cast,
  'Your marks': groups.mark,
  'Bluefin zones': groups.bluefin
}, {collapsed:false}).addTo(map);

// --- legend ---
document.getElementById('legend').innerHTML =
  '<div><span class="dot" style="background:#2ecc71"></span>Casting spots</div>'+
  '<div><span class="dot" style="background:#f1c40f"></span>Your marks</div>'+
  '<div><span class="dot" style="background:#e74c3c"></span>Bluefin zones (offshore)</div>'+
  '<div style="margin-top:6px">Water temp</div><div class="bar"></div>'+
  '<div class="s" style="display:flex;justify-content:space-between;color:#7d97ad">'+
  '<span>'+D.tmin.toFixed(1)+'°</span><span>'+D.tmax.toFixed(1)+'°C</span></div>';
</script>
</body></html>"""


if __name__ == "__main__":
    main()
