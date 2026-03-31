# TESTE RÁPIDO DA API
# Cole no terminal ou use ferramentas como Postman/Insomnia

# Substitua BASE_URL pela URL do seu deploy
BASE_URL="https://seu-projeto.vercel.app"

# 1. Verificar status
curl $BASE_URL/

# 2. Fazer login (admin padrão)
TOKEN=$(curl -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@hamburgueria.com",
    "senha": "admin123"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"

# 3. Ver meus dados
curl "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $TOKEN"

# 4. Criar categoria
curl -X POST "$BASE_URL/Pedidos/categorias" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Hambúrgueres",
    "descricao": "Nossos deliciosos hambúrgueres artesanais"
  }'

# 5. Criar produto (use URL de imagem externa)
curl -X POST "$BASE_URL/Produto/produtos" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "X-Burger Classic",
    "descricao": "Hambúrguer artesanal com queijo, alface e tomate",
    "preco": 25.00,
    "categoria_id": 1,
    "imagem_url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=500",
    "disponivel": true
  }'

# 6. Listar produtos
curl "$BASE_URL/Produto/produtos"

# 7. Criar variação para produto
curl -X POST "$BASE_URL/Produto/produtos/1/variacoes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Pro",
    "descricao": "Com bacon e cheddar extra",
    "acrescimo": 5.00
  }'

# 8. Criar pedido
PEDIDO_ID=$(curl -X POST "$BASE_URL/Pedidos/pedidos" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario": 1
  }' | jq -r '.id')

echo "Pedido criado: $PEDIDO_ID"

# 9. Adicionar item ao pedido
curl -X POST "$BASE_URL/Pedidos/pedido/adicionar-item/$PEDIDO_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quantidade": 2,
    "nomedoproduto": "X-Burger Classic",
    "preco_unitario": 25.00,
    "variacao_id": 1
  }'

# 10. Finalizar pedido
curl -X POST "$BASE_URL/Pedidos/pedido/finalizar/$PEDIDO_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "forma_pagamento": "PIX"
  }'

# 11. Ver meus pedidos
curl "$BASE_URL/Pedidos/meus-pedidos" \
  -H "Authorization: Bearer $TOKEN"

# 12. Ver vendas do dia (admin)
curl "$BASE_URL/Vendas/diario" \
  -H "Authorization: Bearer $TOKEN"

# 13. Ver resumo geral (admin)
curl "$BASE_URL/Vendas/resumo" \
  -H "Authorization: Bearer $TOKEN"

# 14. Ver configurações da loja
curl "$BASE_URL/Loja/"

# 15. Atualizar loja (admin)
curl -X PUT "$BASE_URL/Loja/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nome_loja": "Burger House Premium",
    "taxa_entrega": 5.00,
    "telefone": "(85) 99999-9999",
    "endereco_loja": "Rua das Flores, 123 - Fortaleza/CE"
  }'
