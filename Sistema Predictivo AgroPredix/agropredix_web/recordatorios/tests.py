from datetime import timedelta

from django.utils import timezone

from parcelas.tests import crear_distrito, crear_parcela
from recomendaciones.models import Recomendacion, Siembra
from usuarios.base_pruebas import PruebaBase

from . import servicio


class RecordatoriosTests(PruebaBase):
    def setUp(self):
        self.u = self.crear_usuario()
        self.p = crear_parcela(self.u, crear_distrito())
        self.hoy = timezone.localdate()

    def siembra(self, dias_siembra, dias_cierre):
        rec = Recomendacion.objects.create(parcela=self.p, mes=self.hoy.month, resultado=[])
        return Siembra.objects.create(
            recomendacion=rec, cultivo_cod='1001', cultivo='Papa', puesto=1, idoneidad=.8, certeza_pct=70,
            fecha_siembra=self.hoy + timedelta(days=dias_siembra),
            cierre_estimado=self.hoy + timedelta(days=dias_cierre))

    def test_avisa_la_cosecha_cuando_esta_cerca(self):
        self.siembra(-100, 2)
        self.assertEqual([r.tipo for r in servicio.generar(self.hoy)], ['cosecha'])

    def test_no_avisa_si_falta_mucho(self):
        self.siembra(-10, 90)
        self.assertEqual(servicio.generar(self.hoy), [])

    def test_respeta_el_tipo_desactivado(self):
        self.siembra(-100, 2)
        pref = servicio.preferencias_de(self.u)
        pref.avisar_cosecha = False
        pref.save()
        self.assertEqual(servicio.generar(self.hoy), [])

    def test_no_duplica(self):
        self.siembra(-100, 2)
        servicio.generar(self.hoy)
        self.assertEqual(servicio.generar(self.hoy), [])

    def test_canal_app_queda_como_enviado(self):
        self.siembra(-100, 2)
        servicio.generar(self.hoy)
        self.assertEqual(servicio.enviar_pendientes(self.hoy), 1)