Feature: A shop owner joins Fidelia
  A merchant asks to join from Fidelia Pro. Nothing is theirs until an admin
  has called them, seen the shop and checked that the wallet is in their name.

  Scenario: A shop owner asks to join and can sell once approved
    Given Awa asks to join Fidelia for her maquis "Chez Awa" with the number "07 44 55 66 77"
    Then Awa cannot sign in to Fidelia Pro yet
    When an admin approves the request as "Maquis Chez Awa" after calling her, seeing the shop and checking the wallet name
    Then Awa can sign in to Fidelia Pro
    And her shop "Maquis Chez Awa" has a payment QR

  Scenario: An admin cannot approve a shop without the checks
    Given Awa asks to join Fidelia for her maquis "Chez Awa" with the number "07 44 55 66 77"
    When an admin tries to approve the request without checking the wallet name
    Then the approval is refused because the wallet holder was not checked
    And Awa cannot sign in to Fidelia Pro yet
