import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Station } from './types';
import { status } from './domain';
import { Wind } from './components';

export function StationMap({stations, selected, onSelect}: {stations: Station[]; selected: string; onSelect: (id: string) => void}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef(new Map<string, L.Marker>());
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    if (!container.current || !stations.length) return;
    const instance = L.map(container.current, {scrollWheelZoom: false});
    map.current = instance;
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(instance);
    tiles.on('tileerror', () => setTileError(true));
    markers.current.clear();
    for (const station of stations) {
      const tag = status(station.latest);
      const name = station.name || station.station_id;
      const icon = L.divIcon({className: 'station-pin', html: `<span style="--pin-color:${tag.color}"></span>`, iconSize: [28, 28], iconAnchor: [14, 14]});
      const marker = L.marker([station.lat, station.lon], {icon, title: name, keyboard: true});
      // fitBounds initializes this map after the loop, so the icon does not exist
      // until Leaflet's add event. Set its accessible label at that point.
      marker.on('add', () => {
        const element = marker.getElement();
        element?.setAttribute('aria-label', `Show ${name}: ${tag.text}`);
        // Leaflet's Enter handler opens its popup but does not emit click.
        // Activate our station selection for both standard button keys.
        element?.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault(); onSelect(station.station_id); marker.openPopup();
          }
        });
      });
      marker.addTo(instance);
      const popup = document.createElement('div');
      const heading = document.createElement('strong'); heading.textContent = name;
      const classification = document.createElement('p'); classification.textContent = tag.text;
      const open = document.createElement('button'); open.type = 'button'; open.textContent = 'Open station chart';
      open.addEventListener('click', () => onSelect(station.station_id));
      popup.append(heading, classification, open); marker.bindPopup(popup);
      marker.on('click', () => onSelect(station.station_id));
      markers.current.set(station.station_id, marker);
    }
    instance.fitBounds(L.latLngBounds(stations.map(station => [station.lat, station.lon])), {padding: [42, 42], maxZoom: 12});
    const observer = new ResizeObserver(() => instance.invalidateSize()); observer.observe(container.current);
    return () => { observer.disconnect(); instance.remove(); map.current = null; markers.current.clear(); };
  }, [stations, onSelect]);
  useEffect(() => {
    for (const [id, marker] of markers.current) {
      marker.getElement()?.classList.toggle('selected', id === selected);
      marker.setZIndexOffset(id === selected ? 100 : 0);
    }
    const marker = markers.current.get(selected);
    if (marker && map.current && !map.current.getBounds().contains(marker.getLatLng())) map.current.panTo(marker.getLatLng());
  }, [selected, stations]);
  return <div className="map-frame">
    {stations.length ? <><div ref={container} className="station-map" aria-label="Air-quality station map"/>
      <div className="map-wind"><span className="caption">Selected station · wind</span><Wind reading={stations.find(s => s.station_id === selected)?.latest ?? null}/></div>
      {tileError && <div className="tile-notice" role="status">Map tiles unavailable. Station markers and the station list remain available.</div>}</>
      : <div className="empty-map"><span className="map-cross" aria-hidden="true">⊕</span><strong>No stations to plot</strong><p>Station locations appear here when observations are available.</p></div>}
  </div>;
}
