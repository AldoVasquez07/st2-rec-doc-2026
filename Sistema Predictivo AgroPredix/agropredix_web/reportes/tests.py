from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from parcelas.tests import crear_distrito, crear_parcela
from recomendaciones.models import Recomendacion, Siembra
from usuarios.base_pruebas import PruebaBase

from . import servicio


class ReportesTests(PruebaBase):
    n = 0

    def poblar(self, distrito, cantidad):
        hoy, usuarios = timezone.localdate(), []
        for _ in range(cantidad):
            ReportesTests.n += 1
            u = self.crear_usuario(nombre=f'Agricultor {ReportesTests.n}', celular=f'9{ReportesTests.n:08d}')
            rec = Recomendacion.objects.create(
                parcela=crear_parcela(u, distrito), mes=hoy.month,
                resultado=[{'cod': '1001', 'cultivo': 'Papa', 'puesto': 1}])
            Siembra.objects.create(recomendacion=rec, cultivo_cod='1001', cultivo='Papa', puesto=1,
                                   idoneidad=.8, certeza_pct=70, fecha_siembra=hoy,
                                   cierre_estimado=hoy + timedelta(days=120))
            usuarios.append(u)
        return usuarios

    def test_con_pocos_usuarios_no_se_muestra_el_distrito(self):
        d = crear_distrito()
        self.poblar(d, 4)
        r = servicio.reporte_zona(d)
        self.assertFalse(r['hay_datos'])
        self.assertFalse(r['reportes'][0]['visible'])

    def test_con_el_minimo_se_muestra(self):
        d = crear_distrito()
        self.poblar(d, 5)
        r = servicio.reporte_zona(d)
        self.assertTrue(r['hay_datos'])
        self.assertEqual(r['reportes'][0]['sembrados'], {'Papa': 5})
        self.assertEqual(r['reportes'][0]['recomendados'], {'Papa': 5})

    def test_la_pagina_no_expone_nombres_de_otros(self):
        d = crear_distrito()
        usuarios = self.poblar(d, 5)
        self.client.force_login(usuarios[0])
        html = self.client.get(reverse('reportes:zona')).content.decode()
        self.assertNotIn(usuarios[3].nombre, html)

    def test_vecinos_de_la_misma_provincia(self):
        a = crear_distrito()
        b = crear_distrito(ubigeo='040123', nombre='Tiabaya', lat=-16.43, lon=-71.58)
        self.poblar(b, 1)
        self.assertEqual(servicio.vecinos(a), [b])