Feature: Payer en plusieurs fois (layaway)
  A customer pays for one named good in installments. The shop keeps the
  money and hands the good over once the price is reached. It is not credit:
  nobody lends anything.

  Background:
    Given the demo shop is signed in to Fidelia Pro
    And an admin has switched on layaway for the demo shop

  Scenario: A customer pays for a fridge in three installments
    When the shop opens a plan for "Refrigerateur 90 L" at 90000 F for "07 12 34 56 78" with a first payment of 30000 F, after reading the terms to the customer
    Then the plan is open with 60000 F left to pay
    When the shop records a payment of 30000 F
    And the shop records a payment of 30000 F
    Then the plan is paid and waiting for handover
    When the shop hands over the fridge
    Then the plan is delivered
    And the shop's history has one layaway sale of 90000 F
    And the customer sees the delivered plan in the Fidelia app

  Scenario: Nothing is recorded before the customer accepts the terms
    When the shop opens a plan for "Refrigerateur 90 L" at 90000 F for "07 12 34 56 78" with a first payment of 30000 F, without the customer accepting the terms
    Then the plan is refused
    And the shop has no layaway plans

  Scenario: A cancelled plan records the refund and leaves no sale
    When the shop opens a plan for "Refrigerateur 90 L" at 90000 F for "07 12 34 56 78" with a first payment of 30000 F, after reading the terms to the customer
    And the shop cancels the plan and gives back 30000 F
    Then the plan is cancelled with 30000 F refunded
    And no further payment can be recorded on it
    And the shop's history has no layaway sale
