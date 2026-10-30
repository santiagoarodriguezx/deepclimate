import unittest
from unittest.mock import Mock, patch

from backend.services import gibs


class GibsMetadataTests(unittest.TestCase):
    def tearDown(self):
        gibs._cache = None
        gibs._cache_until = 0

    def test_catalog_exposes_provider_legend_and_time_dimensions(self):
        layers = []
        for layer_id, image_format, time_value in [
            ("MODIS_Terra_CorrectedReflectance_TrueColor", "image/jpeg", "2026-10-30/2026-10-30/P1D"),
            ("IMERG_Precipitation_Rate_30min", "image/png", "2026-10-30T10:00:00Z/2026-10-30T11:30:00Z/PT30M"),
        ]:
            layers.append(f"""
            <Layer><ows:Title>{layer_id}</ows:Title><ows:Identifier>{layer_id}</ows:Identifier>
              <Style><ows:Identifier>default</ows:Identifier><LegendURL xlink:role="http://earthdata.nasa.gov/gibs/legend-type/horizontal" xlink:href="https://gibs.example/{layer_id}.svg" /></Style>
              <Dimension><ows:Identifier>Time</ows:Identifier><Default>{time_value.split('/')[1] if layer_id.startswith('IMERG') else '2026-10-30'}</Default><Value>{time_value}</Value></Dimension>
              <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level6</TileMatrixSet></TileMatrixSetLink>
              <Format>{image_format}</Format>
            </Layer>""")
        xml = ("""<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:xlink="http://www.w3.org/1999/xlink"><Contents>"""
               + "".join(layers) + "</Contents></Capabilities>").encode()
        response = Mock(content=xml)
        response.raise_for_status = Mock()
        with patch.object(gibs.httpx, "get", return_value=response):
            catalog = gibs.get_gibs_layers(force_refresh=True)
        imerg = next(layer for layer in catalog["layers"] if layer["id"].startswith("IMERG"))
        self.assertEqual(imerg["legend_url"], "https://gibs.example/IMERG_Precipitation_Rate_30min.svg")
        self.assertEqual(imerg["time_ranges"], ["2026-10-30T10:00:00Z/2026-10-30T11:30:00Z/PT30M"])
        self.assertEqual(imerg["max_zoom"], 6)
        self.assertEqual(imerg["formats"], ["image/png"])


if __name__ == "__main__":
    unittest.main()
