import unittest
from pydantic import ValidationError
from api.schemas import EquipmentPurchaseRequest, EquipmentEquipRequest, EquipmentBoxRequest

class EquipmentSchemaTests(unittest.TestCase):
    def test_purchase_quantity_bounds(self):
        self.assertEqual(EquipmentPurchaseRequest(item_key='iron_sword', quantity=2).quantity, 2)
        with self.assertRaises(ValidationError): EquipmentPurchaseRequest(item_key='iron_sword', quantity=11)

    def test_item_key_format(self):
        with self.assertRaises(ValidationError): EquipmentEquipRequest(item_key='iron sword')

    def test_box_request_id_required_and_safely_formatted(self):
        self.assertEqual(len(EquipmentBoxRequest(request_id='request_123').request_id), 11)
        with self.assertRaises(ValidationError): EquipmentBoxRequest(request_id='short')

if __name__ == '__main__': unittest.main()
